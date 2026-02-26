from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Coroutine
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

import typer
from click.core import ParameterSource
from pydantic import SecretStr

from rsspot.cli_history import HISTORY_MAX_ENTRIES, redact_argv, redacted_command
from rsspot.client import (
    AsyncSpotClient,
    get_client,
    set_default_org,
    set_default_profile,
    set_default_region,
)
from rsspot.client import (
    configure as configure_client,
)
from rsspot.config import load_config
from rsspot.config.manager import ProfileManager
from rsspot.config.models import ProfileConfig
from rsspot.constants import DEFAULT_CLIENT_ID
from rsspot.errors import RSSpotError
from rsspot.models import CloudspaceCreateSpec, OnDemandNodePoolUpsert, SpotNodePoolUpsert
from rsspot.models.nodepools import Autoscaling
from rsspot.pricing_optimizer import (
    build_recommendation,
    filter_rows_for_list,
    list_rows_payload,
    normalize_pricing_items,
    render_build_recommendation_table,
    render_pricing_list_table,
)
from rsspot.utils.output import OutputFormat, emit
from rsspot.utils.serialization import to_plain_data

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Rackspace Spot SDK CLI")
profiles_app = typer.Typer(no_args_is_help=True, help="Manage local account profiles")
organizations_app = typer.Typer(no_args_is_help=True, help="Organization APIs")
regions_app = typer.Typer(no_args_is_help=True, help="Region APIs")
server_classes_app = typer.Typer(no_args_is_help=True, help="Server-class APIs")
pricing_app = typer.Typer(no_args_is_help=True, help="Pricing APIs")
cloudspaces_app = typer.Typer(no_args_is_help=True, help="Cloudspace APIs")
inventory_app = typer.Typer(no_args_is_help=True, help="Inventory APIs")
nodepools_app = typer.Typer(no_args_is_help=True, help="Nodepool APIs")
spot_pools_app = typer.Typer(no_args_is_help=True, help="Spot nodepool APIs")
ondemand_pools_app = typer.Typer(no_args_is_help=True, help="On-demand nodepool APIs")
config_app = typer.Typer(no_args_is_help=True, help="Config and preference commands")
config_history_app = typer.Typer(no_args_is_help=True, help="CLI history preferences")

app.add_typer(profiles_app, name="profiles")
app.add_typer(organizations_app, name="organizations")
app.add_typer(regions_app, name="regions")
app.add_typer(server_classes_app, name="server-classes")
app.add_typer(pricing_app, name="pricing")
app.add_typer(cloudspaces_app, name="cloudspaces")
app.add_typer(inventory_app, name="inventory")
app.add_typer(nodepools_app, name="nodepools")
app.add_typer(config_app, name="config")
config_app.add_typer(config_history_app, name="history")
nodepools_app.add_typer(spot_pools_app, name="spot")
nodepools_app.add_typer(ondemand_pools_app, name="ondemand")


class CLIState:
    def __init__(
        self,
        *,
        profile: str | None,
        config_file: Path | None,
        output: OutputFormat,
        output_explicit: bool,
    ) -> None:
        self.profile = profile
        self.config_file = config_file
        self.output = output
        self.output_explicit = output_explicit


T = TypeVar("T")


def _run(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def _state(ctx: typer.Context) -> CLIState:
    obj = ctx.obj
    if not isinstance(obj, CLIState):
        raise typer.BadParameter("CLI context was not initialized")
    return obj


def _emit(value: Any, *, output: OutputFormat) -> None:
    emit(to_plain_data(value), output=output)


def _pricing_output_mode(state: CLIState) -> OutputFormat:
    if state.output_explicit:
        return state.output
    return "table"


def _parse_key_values(entries: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise typer.BadParameter(f"expected key=value format, got: {entry}")
        key, value = entry.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def _version_callback(value: bool) -> None:
    if value:
        typer.echo("rsspot 0.3.0")
        raise typer.Exit()


def _in_completion_context() -> bool:
    return "_RSSPOT_COMPLETE" in os.environ or "RSSPOT_COMPLETE" in os.environ


def _record_history(ctx: typer.Context, state: CLIState) -> None:
    if _in_completion_context():
        return

    args = ["rsspot", *ctx.args]
    if len(args) <= 1:
        return

    try:
        client = get_client(profile=state.profile)
        redacted_argv = redact_argv(args)
        command = redacted_command(args)
        client.state.history_add(
            command=command,
            argv=redacted_argv,
            profile=client.profile_name,
            org=None,
            region=None,
            max_entries=HISTORY_MAX_ENTRIES,
        )
    except Exception:
        return


_CONFIG_REDACTED = "<redacted>"
_SENSITIVE_CONFIG_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "passphrase",
    "private_key",
    "service_account_key",
    "cert",
    "authorization",
    "header",
    "cookie",
    "jwt",
    "signature",
)


def _is_sensitive_config_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_CONFIG_KEY_MARKERS)


def _redact_sensitive_config(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_config_key(str(key)):
                redacted[str(key)] = _CONFIG_REDACTED
            else:
                redacted[str(key)] = _redact_sensitive_config(item)
        return redacted

    if isinstance(value, list):
        return [_redact_sensitive_config(item) for item in value]

    return value


@app.callback()
def main(
    ctx: typer.Context,
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="Profile name")] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config-file", "-c", help="Path to profile config file"),
    ] = None,
    output: Annotated[OutputFormat, typer.Option("--output", "-o", help="Output format")] = "json",
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version"),
    ] = None,
) -> None:
    _ = version
    configure_client(config_path=config_file)
    source = ctx.get_parameter_source("output")
    output_explicit = source is not None and source is not ParameterSource.DEFAULT
    state = CLIState(profile=profile, config_file=config_file, output=output, output_explicit=output_explicit)
    ctx.obj = state
    _record_history(ctx, state)


def _make_client(state: CLIState) -> AsyncSpotClient:
    return AsyncSpotClient(profile=state.profile, config_path=state.config_file)


@app.command("configure")
def configure(
    ctx: typer.Context,
    profile: Annotated[str, typer.Option(help="Profile name to write")] = "default",
    org: Annotated[str | None, typer.Option(help="Organization name")] = None,
    org_id: Annotated[str | None, typer.Option(help="Organization id (org-...)")] = None,
    region: Annotated[str | None, typer.Option(help="Default region")] = None,
    refresh_token: Annotated[str | None, typer.Option(help="Rackspace Spot refresh token")] = None,
    access_token: Annotated[str | None, typer.Option(help="Optional id_token seed")] = None,
    client_id: Annotated[str, typer.Option(help="OAuth client id")] = DEFAULT_CLIENT_ID,
    base_url: Annotated[str, typer.Option(help="Spot API base URL")] = "https://spot.rackspace.com",
    oauth_url: Annotated[str, typer.Option(help="OAuth base URL")] = "https://login.spot.rackspace.com",
    activate: Annotated[bool, typer.Option("--activate/--no-activate")] = True,
) -> None:
    state = _state(ctx)
    manager = ProfileManager(state.config_file)
    model = ProfileConfig(
        org=org,
        org_id=org_id,
        region=region,
        refresh_token=SecretStr(refresh_token) if refresh_token else None,
        access_token=SecretStr(access_token) if access_token else None,
        client_id=client_id,
        base_url=base_url,
        oauth_url=oauth_url,
    )
    cfg = manager.upsert_profile(profile, model, activate=activate)
    _emit(cfg, output=state.output)


@profiles_app.command("list")
def profiles_list(ctx: typer.Context) -> None:
    state = _state(ctx)
    manager = ProfileManager(state.config_file)
    names = manager.list_profiles()
    _emit({"active_profile": manager.load().active_profile, "profiles": names}, output=state.output)


@profiles_app.command("show")
def profiles_show(
    ctx: typer.Context,
    name: Annotated[str | None, typer.Argument(help="Profile name")] = None,
) -> None:
    state = _state(ctx)
    manager = ProfileManager(state.config_file)
    profile = manager.get_profile(name)
    _emit(profile, output=state.output)


@profiles_app.command("use")
def profiles_use(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Profile name")],
) -> None:
    state = _state(ctx)
    manager = ProfileManager(state.config_file)
    cfg = manager.set_active_profile(name)
    _emit(cfg, output=state.output)


@profiles_app.command("delete")
def profiles_delete(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Profile name")],
) -> None:
    state = _state(ctx)
    manager = ProfileManager(state.config_file)
    cfg = manager.delete_profile(name)
    _emit(cfg, output=state.output)


@organizations_app.command("list")
def organizations_list(ctx: typer.Context) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.organizations.list()

    _emit(_run(run()), output=state.output)


@organizations_app.command("get")
def organizations_get(ctx: typer.Context, name_or_id: Annotated[str, typer.Argument()]) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.organizations.get(name_or_id)

    _emit(_run(run()), output=state.output)


@regions_app.command("list")
def regions_list(ctx: typer.Context) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.regions.list()

    _emit(_run(run()), output=state.output)


@regions_app.command("get")
def regions_get(ctx: typer.Context, name: Annotated[str, typer.Argument()]) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.regions.get(name)

    _emit(_run(run()), output=state.output)


@server_classes_app.command("list")
def server_classes_list(
    ctx: typer.Context,
    region: Annotated[str | None, typer.Option(help="Filter by region")] = None,
    only_available: Annotated[bool, typer.Option("--only-available/--all")] = True,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.server_classes.list(region=region, only_available=only_available)

    _emit(_run(run()), output=state.output)


@server_classes_app.command("get")
def server_classes_get(ctx: typer.Context, name: Annotated[str, typer.Argument()]) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.server_classes.get(name)

    _emit(_run(run()), output=state.output)


@pricing_app.command("list")
def pricing_list(
    ctx: typer.Context,
    region: Annotated[str | None, typer.Option(help="Filter by region")] = None,
    nodes: Annotated[int, typer.Option("--nodes", min=1, help="Node multiplier for pricing display")] = 1,
    min_cpu: Annotated[int | None, typer.Option("--min-cpu", help="Minimum vCPU")] = None,
    max_cpu: Annotated[int | None, typer.Option("--max-cpu", help="Maximum vCPU")] = None,
    class_filter: Annotated[
        list[str] | None,
        typer.Option("--class", help="Class filter(s), repeatable or comma-separated (gp,ch,mh)"),
    ] = None,
    gen: Annotated[int | None, typer.Option("--gen", min=1, max=2, help="Virtual generation filter")] = None,
) -> None:
    state = _state(ctx)
    if min_cpu is not None and max_cpu is not None and min_cpu > max_cpu:
        raise typer.BadParameter("--min-cpu cannot be greater than --max-cpu")

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.pricing.list(region=region)

    result = _run(run())
    rows = normalize_pricing_items(result.items)
    rows = filter_rows_for_list(
        rows,
        class_filters=class_filter,
        gen=gen,
        min_cpu=float(min_cpu) if min_cpu is not None else None,
        max_cpu=float(max_cpu) if max_cpu is not None else None,
    )

    output_mode = _pricing_output_mode(state)
    if output_mode in {"json", "yaml"}:
        _emit(list_rows_payload(rows, nodes=nodes), output=output_mode)
        return

    render_pricing_list_table(rows, nodes=nodes)


@pricing_app.command("get")
def pricing_get(ctx: typer.Context, server_class: Annotated[str, typer.Argument()]) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.pricing.for_server_class(server_class)

    _emit(_run(run()), output=state.output)


@pricing_app.command("build")
def pricing_build(
    ctx: typer.Context,
    nodes: Annotated[int, typer.Option("--nodes", min=1, help="Desired total node count")],
    gen: Annotated[int | None, typer.Option("--gen", min=1, max=2, help="Virtual generation filter")] = None,
    risk: Annotated[
        Literal["low", "med", "high"],
        typer.Option("--risk", help="Bid/risk tuning level"),
    ] = "med",
    balanced: Annotated[
        bool,
        typer.Option("--balanced/--single", help="Spread balanced strategy across multiple pools"),
    ] = False,
    regions: Annotated[
        list[str] | None,
        typer.Option("--regions", help="Region filter(s), repeatable or comma-separated"),
    ] = None,
    classes: Annotated[
        list[str] | None,
        typer.Option("--classes", help="Class filter(s), repeatable or comma-separated"),
    ] = None,
    min_hour: Annotated[float | None, typer.Option("--min-hour", min=0.0, help="Minimum cluster hourly spend")] = None,
    max_hour: Annotated[float | None, typer.Option("--max-hour", min=0.0, help="Maximum cluster hourly spend")] = None,
    min_month: Annotated[
        float | None,
        typer.Option("--min-month", min=0.0, help="Minimum cluster monthly spend"),
    ] = None,
    max_month: Annotated[
        float | None,
        typer.Option("--max-month", min=0.0, help="Maximum cluster monthly spend"),
    ] = None,
) -> None:
    state = _state(ctx)
    if min_hour is not None and max_hour is not None and min_hour > max_hour:
        raise typer.BadParameter("--min-hour cannot be greater than --max-hour")
    if min_month is not None and max_month is not None and min_month > max_month:
        raise typer.BadParameter("--min-month cannot be greater than --max-month")

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.pricing.list()

    result = _run(run())
    rows = normalize_pricing_items(result.items)
    recommendation = build_recommendation(
        rows,
        nodes=nodes,
        gen=gen,
        risk=risk,
        balanced=balanced,
        regions=regions,
        classes=classes,
        min_hour=min_hour,
        max_hour=max_hour,
        min_month=min_month,
        max_month=max_month,
    )

    output_mode = _pricing_output_mode(state)
    if output_mode in {"json", "yaml"}:
        _emit(recommendation, output=output_mode)
        return

    render_build_recommendation_table(recommendation)


@cloudspaces_app.command("list")
def cloudspaces_list(
    ctx: typer.Context,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.cloudspaces.list(org=org)

    _emit(_run(run()), output=state.output)


@cloudspaces_app.command("get")
def cloudspaces_get(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.cloudspaces.get(name, org=org)

    _emit(_run(run()), output=state.output)


@cloudspaces_app.command("create")
def cloudspaces_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="Cloudspace name")],
    region: Annotated[str, typer.Option(help="Region")],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
    kubernetes_version: Annotated[str, typer.Option(help="Kubernetes version")] = "1.31.1",
    deployment_type: Annotated[str, typer.Option(help="Deployment type")] = "gen2",
    cni: Annotated[str, typer.Option(help="CNI plugin")] = "calico",
    cloud: Annotated[str, typer.Option(help="Cloud type")] = "default",
    ha_control_plane: Annotated[bool, typer.Option(help="Enable HA control plane")] = False,
    gpu_enabled: Annotated[bool, typer.Option(help="Enable GPU support")] = False,
) -> None:
    state = _state(ctx)
    spec = CloudspaceCreateSpec(
        name=name,
        region=region,
        kubernetes_version=kubernetes_version,
        deployment_type=deployment_type,
        cni=cni,
        cloud=cloud,
        ha_control_plane=ha_control_plane,
        gpu_enabled=gpu_enabled,
    )

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.cloudspaces.create(spec, org=org)

    _emit(_run(run()), output=state.output)


@cloudspaces_app.command("delete")
def cloudspaces_delete(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.cloudspaces.delete(name, org=org)

    _emit(_run(run()), output=state.output)


@cloudspaces_app.command("get-config")
def cloudspaces_get_config(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Cloudspace name")],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
    output_file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Write kubeconfig to file"),
    ] = None,
) -> None:
    state = _state(ctx)

    async def run() -> str:
        async with _make_client(state) as client:
            return await client.cloudspaces.generate_kubeconfig(name, org=org)

    kubeconfig = _run(run())
    if output_file is not None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(kubeconfig, encoding="utf-8")
        typer.echo(f"wrote kubeconfig to {output_file}")
    else:
        typer.echo(kubeconfig)


@inventory_app.command("vmcloudspaces")
def inventory_vmcloudspaces(
    ctx: typer.Context,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.inventory.list_vmcloudspaces(org=org)

    _emit(_run(run()), output=state.output)


@inventory_app.command("vmpools")
def inventory_vmpools(
    ctx: typer.Context,
    vmcloudspace: Annotated[str, typer.Option(help="VM cloudspace label")],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.inventory.list_vmpools(vmcloudspace=vmcloudspace, org=org)

    _emit(_run(run()), output=state.output)


@inventory_app.command("events")
def inventory_events(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(help="Max events to fetch")] = 100,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.inventory.list_organization_events(limit=limit)

    _emit(_run(run()), output=state.output)


def _build_autoscaling(enabled: bool, min_nodes: int, max_nodes: int) -> Autoscaling:
    return Autoscaling(enabled=enabled, minNodes=min_nodes, maxNodes=max_nodes)


@spot_pools_app.command("list")
def spot_pools_list(
    ctx: typer.Context,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
    cloudspace: Annotated[str | None, typer.Option(help="Filter by cloudspace")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.spot_nodepools.list(org=org, cloudspace=cloudspace)

    _emit(_run(run()), output=state.output)


@spot_pools_app.command("get")
def spot_pools_get(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.spot_nodepools.get(name, org=org)

    _emit(_run(run()), output=state.output)


@spot_pools_app.command("create")
def spot_pools_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="Nodepool name")],
    cloudspace: Annotated[str, typer.Option(help="Cloudspace name")],
    server_class: Annotated[str, typer.Option(help="Server class")],
    bid_price: Annotated[str, typer.Option(help="Bid price, e.g. 0.08")],
    desired: Annotated[int, typer.Option(help="Desired node count")] = 1,
    autoscaling_enabled: Annotated[bool, typer.Option("--autoscaling/--no-autoscaling")] = False,
    autoscaling_min: Annotated[int, typer.Option(help="Autoscaling min nodes")] = 0,
    autoscaling_max: Annotated[int, typer.Option(help="Autoscaling max nodes")] = 0,
    label: Annotated[list[str] | None, typer.Option("--label", help="Custom label key=value")] = None,
    annotation: Annotated[
        list[str] | None,
        typer.Option("--annotation", help="Custom annotation key=value"),
    ] = None,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)
    spec = SpotNodePoolUpsert(
        name=name,
        cloudspace=cloudspace,
        server_class=server_class,
        desired=desired,
        bid_price=bid_price,
        custom_labels=_parse_key_values(label or []),
        custom_annotations=_parse_key_values(annotation or []),
        autoscaling=_build_autoscaling(autoscaling_enabled, autoscaling_min, autoscaling_max),
    )

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.spot_nodepools.create(spec, org=org)

    _emit(_run(run()), output=state.output)


@spot_pools_app.command("update")
def spot_pools_update(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="Nodepool name")],
    cloudspace: Annotated[str, typer.Option(help="Cloudspace name")],
    server_class: Annotated[str, typer.Option(help="Server class")],
    bid_price: Annotated[str, typer.Option(help="Bid price, e.g. 0.08")],
    desired: Annotated[int, typer.Option(help="Desired node count")] = 1,
    autoscaling_enabled: Annotated[bool, typer.Option("--autoscaling/--no-autoscaling")] = False,
    autoscaling_min: Annotated[int, typer.Option(help="Autoscaling min nodes")] = 0,
    autoscaling_max: Annotated[int, typer.Option(help="Autoscaling max nodes")] = 0,
    label: Annotated[list[str] | None, typer.Option("--label", help="Custom label key=value")] = None,
    annotation: Annotated[
        list[str] | None,
        typer.Option("--annotation", help="Custom annotation key=value"),
    ] = None,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)
    spec = SpotNodePoolUpsert(
        name=name,
        cloudspace=cloudspace,
        server_class=server_class,
        desired=desired,
        bid_price=bid_price,
        custom_labels=_parse_key_values(label or []),
        custom_annotations=_parse_key_values(annotation or []),
        autoscaling=_build_autoscaling(autoscaling_enabled, autoscaling_min, autoscaling_max),
    )

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.spot_nodepools.update(spec, org=org)

    _emit(_run(run()), output=state.output)


@spot_pools_app.command("delete")
def spot_pools_delete(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.spot_nodepools.delete(name, org=org)

    _emit(_run(run()), output=state.output)


@ondemand_pools_app.command("list")
def ondemand_pools_list(
    ctx: typer.Context,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
    cloudspace: Annotated[str | None, typer.Option(help="Filter by cloudspace")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.ondemand_nodepools.list(org=org, cloudspace=cloudspace)

    _emit(_run(run()), output=state.output)


@ondemand_pools_app.command("get")
def ondemand_pools_get(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.ondemand_nodepools.get(name, org=org)

    _emit(_run(run()), output=state.output)


@ondemand_pools_app.command("create")
def ondemand_pools_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="Nodepool name")],
    cloudspace: Annotated[str, typer.Option(help="Cloudspace name")],
    server_class: Annotated[str, typer.Option(help="Server class")],
    desired: Annotated[int, typer.Option(help="Desired node count")] = 1,
    autoscaling_enabled: Annotated[bool, typer.Option("--autoscaling/--no-autoscaling")] = False,
    autoscaling_min: Annotated[int, typer.Option(help="Autoscaling min nodes")] = 0,
    autoscaling_max: Annotated[int, typer.Option(help="Autoscaling max nodes")] = 0,
    label: Annotated[list[str] | None, typer.Option("--label", help="Custom label key=value")] = None,
    annotation: Annotated[
        list[str] | None,
        typer.Option("--annotation", help="Custom annotation key=value"),
    ] = None,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)
    spec = OnDemandNodePoolUpsert(
        name=name,
        cloudspace=cloudspace,
        server_class=server_class,
        desired=desired,
        custom_labels=_parse_key_values(label or []),
        custom_annotations=_parse_key_values(annotation or []),
        autoscaling=_build_autoscaling(autoscaling_enabled, autoscaling_min, autoscaling_max),
    )

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.ondemand_nodepools.create(spec, org=org)

    _emit(_run(run()), output=state.output)


@ondemand_pools_app.command("update")
def ondemand_pools_update(
    ctx: typer.Context,
    name: Annotated[str, typer.Option(help="Nodepool name")],
    cloudspace: Annotated[str, typer.Option(help="Cloudspace name")],
    server_class: Annotated[str, typer.Option(help="Server class")],
    desired: Annotated[int, typer.Option(help="Desired node count")] = 1,
    autoscaling_enabled: Annotated[bool, typer.Option("--autoscaling/--no-autoscaling")] = False,
    autoscaling_min: Annotated[int, typer.Option(help="Autoscaling min nodes")] = 0,
    autoscaling_max: Annotated[int, typer.Option(help="Autoscaling max nodes")] = 0,
    label: Annotated[list[str] | None, typer.Option("--label", help="Custom label key=value")] = None,
    annotation: Annotated[
        list[str] | None,
        typer.Option("--annotation", help="Custom annotation key=value"),
    ] = None,
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)
    spec = OnDemandNodePoolUpsert(
        name=name,
        cloudspace=cloudspace,
        server_class=server_class,
        desired=desired,
        custom_labels=_parse_key_values(label or []),
        custom_annotations=_parse_key_values(annotation or []),
        autoscaling=_build_autoscaling(autoscaling_enabled, autoscaling_min, autoscaling_max),
    )

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.ondemand_nodepools.update(spec, org=org)

    _emit(_run(run()), output=state.output)


@ondemand_pools_app.command("delete")
def ondemand_pools_delete(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument()],
    org: Annotated[str | None, typer.Option(help="Organization name or id")] = None,
) -> None:
    state = _state(ctx)

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client.ondemand_nodepools.delete(name, org=org)

    _emit(_run(run()), output=state.output)


@config_app.command("info")
def config_info(ctx: typer.Context) -> None:
    state = _state(ctx)
    cfg = load_config(config_path=state.config_file)
    client = get_client(profile=state.profile)
    payload = _redact_sensitive_config(cfg.data.model_dump(mode="json"))
    payload["_source"] = cfg.source
    payload["_path"] = str(cfg.path) if cfg.path else None
    payload["_state"] = {
        "history_count": client.state.history_count(),
        "history_max_entries": HISTORY_MAX_ENTRIES,
    }
    _emit(payload, output=state.output)


@config_app.command("set-default-profile")
def config_set_default_profile(name: str) -> None:
    set_default_profile(name)
    typer.echo(f"default profile set to {name}")


@config_app.command("set-default-org")
def config_set_default_org(name: str) -> None:
    set_default_org(name)
    typer.echo(f"default org set to {name}")


@config_app.command("set-default-region")
def config_set_default_region(name: str) -> None:
    set_default_region(name)
    typer.echo(f"default region set to {name}")


@config_history_app.command("info")
def config_history_info(ctx: typer.Context) -> None:
    state = _state(ctx)
    client = get_client(profile=state.profile)
    payload = {
        "enabled": True,
        "max_entries": HISTORY_MAX_ENTRIES,
        "count": client.state.history_count(),
    }
    _emit(payload, output=state.output)


@config_history_app.command("clear")
def config_history_clear(ctx: typer.Context) -> None:
    state = _state(ctx)
    client = get_client(profile=state.profile)
    client.state.history_clear()
    typer.echo("cleared command history")


@app.command("raw")
def raw(
    ctx: typer.Context,
    method: Annotated[str, typer.Option(help="HTTP method")] = "GET",
    path: Annotated[str, typer.Option(help="API path, e.g. /apis/ngpc.rxt.io/v1/regions")] = "/",
    params_json: Annotated[str | None, typer.Option(help="JSON object query params")] = None,
    body_json: Annotated[str | None, typer.Option(help="JSON object request body")] = None,
) -> None:
    state = _state(ctx)
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None

    if params_json:
        parsed_params = json.loads(params_json)
        if not isinstance(parsed_params, dict):
            raise typer.BadParameter("params-json must be a JSON object")
        params = parsed_params

    if body_json:
        parsed_body = json.loads(body_json)
        if not isinstance(parsed_body, dict):
            raise typer.BadParameter("body-json must be a JSON object")
        body = parsed_body

    async def run() -> Any:
        async with _make_client(state) as client:
            return await client._request_json(method, path, params=params, json_data=body)

    _emit(_run(run()), output=state.output)


def run() -> None:
    try:
        app()
    except RSSpotError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    run()
