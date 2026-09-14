"""Streamlit 기반 AirKorea API 디버그/fixture 뷰어."""
# ruff: noqa: E402,I001

from __future__ import annotations

import asyncio

import inspect
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
for module_name, module in list(sys.modules.items()):
    if module_name != "airkorea" and not module_name.startswith("airkorea."):
        continue
    module_file = getattr(module, "__file__", None)
    if module_file is not None and not Path(module_file).resolve().is_relative_to(SRC):
        del sys.modules[module_name]

try:
    import pandas as pd
    import streamlit as st
except ModuleNotFoundError as exc:  # pragma: no cover - 선택 실행 도구
    raise SystemExit('Streamlit UI를 쓰려면 `pip install -e ".[debug-ui]"`를 실행하세요.') from exc

from airkorea import (
    DEBUGGABLE_METHODS,
    AirKoreaClient,
    DebugRun,
    ParamSpec,
    __version__,
    api_catalog_dicts,
    api_catalog_params_for_method,
    jsonable,
    load_service_key,
    normalize_service_key,
    run_debug_method,
    save_debug_fixture,
)

DATA_SOURCE = "AirKorea (data.go.kr)"
DATA_SOURCES = (DATA_SOURCE,)


def main() -> None:
    st.set_page_config(page_title="AirKorea Debug UI", layout="wide")
    st.title("AirKorea Debug UI")

    catalog_rows = api_catalog_dicts()
    method_options = _method_options(catalog_rows)

    with st.sidebar:
        st.subheader("Data source")
        data_source = st.selectbox("Data source", DATA_SOURCES)
        st.caption(f"{data_source}를 통해 제공되는 API 목록입니다.")

        st.subheader("API")
        selected_function = st.selectbox("API", method_options)
        selected_catalog = _catalog_for_method(catalog_rows, selected_function)

        what_it_does, return_desc = _api_captions(selected_function)
        st.caption(what_it_does)
        if return_desc:
            st.caption(return_desc)

        loaded_key = load_service_key()
        st.subheader("Environment")
        environment = st.selectbox(
            "Environment",
            ["env", "manual"],
            index=0 if loaded_key else 1,
        )

        st.subheader("Auth")
        if environment == "manual":
            service_key_input = st.text_input(
                "serviceKey",
                value="",
                type="password",
                placeholder="직접 입력",
                help="DATA_GO_KR_SERVICE_KEY 환경변수 또는 .env 값도 사용할 수 있습니다.",
            )
            effective_service_key = service_key_input
        else:
            effective_service_key = loaded_key
            if loaded_key:
                st.caption("DATA_GO_KR_SERVICE_KEY 값을 사용합니다. Source: process env 또는 .env")
            else:
                st.warning("DATA_GO_KR_SERVICE_KEY 값을 찾지 못했습니다.")
        _service_key_links(selected_catalog)

        timeout = st.number_input(
            "Timeout",
            min_value=1.0,
            max_value=60.0,
            value=10.0,
            step=1.0,
            help="API 요청 timeout seconds입니다.",
        )
        fixture_base_dir = _fixture_base_dir_sidebar()

    tabs = st.tabs(
        [
            "Raw Response",
            "Pydantic Model",
            "Processed Result",
            "Validation Errors",
            "Debug Trace",
            "Fixture / Testcase",
        ]
    )

    with tabs[0]:
        _raw_response_tab(
            data_source,
            selected_function,
            selected_catalog,
            catalog_rows,
            effective_service_key,
            float(timeout),
        )
    with tabs[1]:
        _pydantic_model_tab(data_source, selected_function)
    with tabs[2]:
        _processed_result_tab(data_source, selected_function)
    with tabs[3]:
        _validation_errors_tab(data_source, selected_function)
    with tabs[4]:
        _debug_trace_tab(catalog_rows, data_source, selected_function, selected_catalog)
    with tabs[5]:
        _fixture_tab(_current_debug_run(data_source, selected_function), fixture_base_dir)


def _api_captions(function_name: str) -> tuple[str, str]:
    """(무엇을 하는 API인지, 어떤 데이터를 반환하는지) 캡션 2줄을 함수 docstring/타입에서 만듭니다.

    함수 이름별 하드코딩 설명 대신 ``AirKoreaClient``의 실제 docstring과 반환
    타입 annotation을 그대로 읽어 새 method가 추가돼도 따로 손댈 필요가 없습니다.
    """

    method = getattr(AirKoreaClient, function_name, None)
    if method is None:
        return (f"{function_name} API입니다.", "")
    what_it_does = inspect.getdoc(method) or f"{function_name} API입니다."
    annotation = inspect.signature(method).return_annotation
    if annotation is inspect.Signature.empty:
        return (what_it_does, "")
    return (what_it_does, f"반환 타입: {annotation}")


def _run(
    data_source: str,
    selected_function: str,
    input_data: dict[str, Any],
    service_key: str | None,
    timeout: float,
) -> None:
    normalized_key = normalize_service_key(service_key or "")
    if not normalized_key:
        st.session_state.pop("last_run", None)
        st.error("서비스키가 필요합니다. 환경변수, .env, 또는 사이드바 입력을 확인하세요.")
        return

    async def fetch() -> DebugRun:
        async with AirKoreaClient(
            service_key=normalized_key, timeout=timeout, retries=0,
        ) as client:
            return await run_debug_method(client, selected_function, input_data)

    run = asyncio.run(fetch())
    _store_debug_run(data_source, selected_function, run)


def _raw_response_tab(
    data_source: str,
    selected_function: str,
    selected_catalog: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    service_key: str | None,
    timeout: float,
) -> None:
    st.subheader(_selected_dataset_name(selected_function, selected_catalog))
    st.caption(_api_full_name(selected_function, selected_catalog))

    try:
        submitted, input_data, missing = _request_form(selected_function, catalog_rows)
    except ValueError as exc:
        st.error(str(exc))
        return

    if selected_function == "call":
        _service_key_links(_call_catalog_for_input(input_data, catalog_rows))

    st.subheader("Request params preview")
    st.json(input_data)

    if submitted:
        if missing:
            st.error("필수 파라미터를 입력하세요: " + ", ".join(missing))
        else:
            _run(data_source, selected_function, input_data, service_key, timeout)

    debug_run = _current_debug_run(data_source, selected_function)
    if debug_run is None:
        st.info("Run selected API를 누르면 raw response를 확인합니다.")
        return

    if debug_run.error:
        st.error(debug_run.error.get("message") or "API 실행 중 오류가 발생했습니다.")
    st.json(jsonable(debug_run.response))


def _request_form(
    selected_function: str,
    catalog_rows: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], list[str]]:
    key_prefix = f"{DATA_SOURCE}:{selected_function}"

    with st.form(f"request-form:{key_prefix}"):
        if selected_function == "call":
            st.subheader("Required parameters")
            required_specs: tuple[ParamSpec, ...] = ()
            form_input = _call_input_form(catalog_rows)
        else:
            specs = api_catalog_params_for_method(selected_function)
            required_specs = tuple(spec for spec in specs if spec.required)
            optional_specs = tuple(spec for spec in specs if not spec.required)
            form_input = {}

            st.subheader("Required parameters")
            if required_specs:
                form_input.update(_render_param_grid(required_specs, key_prefix=key_prefix))
            else:
                st.caption("이 API는 라이브러리 호출 기준의 필수 파라미터가 없습니다.")

            st.subheader("Optional parameters")
            form_input.update(_render_param_grid(optional_specs, key_prefix=key_prefix))

        extra_text = st.text_area(
            "Extra kwargs JSON",
            value="{}",
            height=110,
            help="폼에 없는 라이브러리 kwargs를 JSON object로 추가하거나 같은 key를 덮어씁니다.",
            key=f"{key_prefix}:extra",
        )
        submitted = st.form_submit_button("Run selected API")

    extra_params = _parse_extra_params(extra_text)
    input_data = {**form_input, **extra_params}
    missing = [
        spec.name
        for spec in required_specs
        if not str(input_data.get(spec.name, "")).strip()
    ]
    return submitted, input_data, missing


def _render_param_grid(specs: tuple[ParamSpec, ...], *, key_prefix: str) -> dict[str, Any]:
    """``ParamSpec.kind``만으로 위젯을 고르는 제네릭 렌더러입니다.

    함수 이름을 분기하지 않고, 카탈로그가 준 명세(``kind``/``options``/``default``)로만
    위젯 종류를 결정합니다.
    """

    values: dict[str, Any] = {}
    if not specs:
        st.caption("해당 파라미터가 없습니다.")
        return values

    columns = st.columns(2)
    for index, spec in enumerate(specs):
        with columns[index % 2]:
            value = _param_widget(spec, key=f"{key_prefix}:param:{spec.name}")
            if value is not None and value != "":
                values[spec.name] = value
    return values


def _param_widget(spec: ParamSpec, *, key: str) -> Any:
    if spec.kind == "select":
        options = list(spec.options)
        index = options.index(spec.default) if spec.default in options else 0
        value = st.selectbox(spec.label, options, index=index, key=key, help=spec.help)
        return None if value == "" else value

    if spec.kind == "int":
        min_value = int(spec.min_value) if spec.min_value is not None else 1
        default = int(spec.default) if spec.default is not None else min_value
        return int(
            st.number_input(
                spec.label,
                min_value=min_value,
                value=default,
                step=1,
                key=key,
                help=spec.help,
            )
        )

    if spec.kind == "float":
        default_float = float(spec.default) if spec.default is not None else 0.0
        return float(
            st.number_input(
                spec.label,
                value=default_float,
                key=key,
                help=spec.help,
            )
        )

    text_value = st.text_input(
        spec.label,
        value=str(spec.default or ""),
        key=key,
        help=spec.help,
    )
    return text_value.strip()


def _parse_extra_params(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Extra kwargs JSON 오류: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Extra kwargs JSON은 object여야 합니다.")
    return parsed


def _store_debug_run(data_source: str, selected_function: str, run: Any) -> None:
    st.session_state["last_run"] = {
        "selection_key": _selection_key(data_source, selected_function),
        "run": run,
    }


def _current_debug_run(data_source: str, selected_function: str) -> Any | None:
    stored = st.session_state.get("last_run")
    if not isinstance(stored, dict):
        return None
    if stored.get("selection_key") != _selection_key(data_source, selected_function):
        return None
    return stored.get("run")


def _selection_key(data_source: str, selected_function: str) -> str:
    return f"{data_source}:{selected_function}"


def _fixture_tab(debug_run: Any, fixture_base_dir: str) -> None:
    if debug_run is None:
        st.info("실행 후 fixture로 저장할 수 있습니다.")
        st.caption("Fixture base dir")
        st.code(fixture_base_dir, language=None)
        return

    with st.form("fixture_form"):
        case_name = st.text_input("Case name", value=f"{debug_run.function}_case")
        description = st.text_area("Description", value="")
        assertion_mode = st.selectbox(
            "Assertion mode",
            ["snapshot", "schema_only", "required_fields", "count"],
        )
        exclude_fields = st.text_input(
            "Exclude fields",
            value="fetched_at, request_id, updated_at, collected_at",
        )
        required_fields = st.text_input("Required fields", value="")
        base_dir = st.text_input("Fixture base dir", value=fixture_base_dir)
        overwrite = st.checkbox("Overwrite existing fixture", value=False)
        submitted = st.form_submit_button("Save as fixture")

    if not submitted:
        return

    assertion = {
        "mode": assertion_mode,
        "exclude_fields": [item.strip() for item in exclude_fields.split(",") if item.strip()],
        "required_fields": [item.strip() for item in required_fields.split(",") if item.strip()],
    }
    try:
        path = save_debug_fixture(
            base_dir=base_dir,
            case_name=case_name,
            description=description,
            assertion=assertion,
            library_version=__version__,
            overwrite=overwrite,
            debug_run=debug_run,
        )
    except Exception as exc:
        st.error(str(exc))
    else:
        st.success(f"Saved: {path}")


def _pydantic_model_tab(data_source: str, selected_function: str) -> None:
    debug_run = _current_debug_run(data_source, selected_function)
    if debug_run is None:
        st.info("Raw Response 탭에서 선택한 API를 실행하면 여기에서 Pydantic 모델을 확인합니다.")
        return
    if debug_run.error:
        st.warning("API 실행 중 오류가 있어 parsed model이 비어 있을 수 있습니다.")
    st.json(jsonable(debug_run.parsed) if debug_run.parsed is not None else {})


def _processed_result_tab(data_source: str, selected_function: str) -> None:
    debug_run = _current_debug_run(data_source, selected_function)
    if debug_run is None:
        st.info("Raw Response 탭에서 API를 실행하면 처리된 row preview를 표시합니다.")
        return

    processed = jsonable(debug_run.processed)
    if isinstance(processed, list) and processed:
        st.dataframe(pd.json_normalize(processed, sep="."), width="stretch", hide_index=True)
    else:
        st.json(processed if processed is not None else {})


def _validation_errors_tab(data_source: str, selected_function: str) -> None:
    debug_run = _current_debug_run(data_source, selected_function)
    if debug_run is None:
        st.info("아직 실행된 API가 없습니다.")
        return
    if debug_run.error:
        st.error(debug_run.error.get("message") or "API 실행 중 오류가 발생했습니다.")
        st.json(debug_run.error)
        return
    st.success("오류 없이 실행됐습니다.")


def _debug_trace_tab(
    catalog_rows: list[dict[str, Any]],
    data_source: str,
    selected_function: str,
    selected_catalog: list[dict[str, Any]],
) -> None:
    debug_run = _current_debug_run(data_source, selected_function)

    st.subheader("Catalog")
    st.dataframe(catalog_rows, width="stretch", hide_index=True)

    st.subheader("Selected API")
    if selected_function == "call":
        selected_rows = list(debug_run.catalog) if debug_run and debug_run.catalog else []
        if selected_rows:
            st.json(selected_rows[0] if len(selected_rows) == 1 else selected_rows)
            _service_key_links(selected_rows)
        else:
            st.info(
                "Raw Response 탭에서 service와 endpoint를 선택해 실행하면 "
                "선택 API를 표시합니다."
            )
    else:
        st.json(selected_catalog[0] if len(selected_catalog) == 1 else selected_catalog)
        _service_key_links(selected_catalog)
    st.caption("credential env: DATA_GO_KR_SERVICE_KEY")

    st.subheader("Trace")
    if debug_run:
        st.code("\n".join(debug_run.trace) or "trace 없음")
    else:
        st.info("아직 실행 trace가 없습니다.")


def _call_input_form(catalog_rows: list[dict[str, Any]]) -> dict[str, Any]:
    service_names = sorted({row["service_name"] for row in catalog_rows})
    service_name = st.selectbox(
        "Service name",
        service_names,
        key="param_call_service_name",
        help="SUPPORTED_ENDPOINTS의 AirKorea 서비스명",
    )
    endpoint_rows = [row for row in catalog_rows if row["service_name"] == service_name]
    endpoints = [row["endpoint"] for row in endpoint_rows]
    endpoint = st.selectbox(
        "Endpoint",
        endpoints,
        key="param_call_endpoint",
        help="공식 endpoint 철자",
    )
    selected_row = next(row for row in endpoint_rows if row["endpoint"] == endpoint)
    st.caption(f"데이터셋: {selected_row['dataset_name']}")

    st.subheader("Optional parameters")
    params_text = st.text_area(
        "params",
        value=json.dumps(_default_call_params(endpoint), ensure_ascii=False, indent=2),
        key="param_call_params",
        help="endpoint별 query parameter object",
    )
    params: dict[str, Any] = {}
    if params_text.strip():
        try:
            parsed = json.loads(params_text)
        except json.JSONDecodeError as exc:
            st.error(f"params JSON 오류: {exc}")
        else:
            if isinstance(parsed, dict):
                params = parsed
            else:
                st.error("params는 JSON object여야 합니다.")

    col1, col2 = st.columns(2)
    with col1:
        page_no = st.number_input(
            "page_no",
            min_value=1,
            value=1,
            step=1,
            key="param_call_page_no",
        )
    with col2:
        num_of_rows = st.number_input(
            "num_of_rows",
            min_value=1,
            value=5,
            step=1,
            key="param_call_num_of_rows",
        )

    return {
        "service_name": service_name,
        "endpoint": endpoint,
        "params": params,
        "page_no": int(page_no),
        "num_of_rows": int(num_of_rows),
    }


def _fixture_base_dir_sidebar() -> str:
    st.subheader("Fixtures")
    candidates = _fixture_dir_candidates()
    options = [str(path) for path in candidates]
    custom_label = "Custom..."
    selected = st.selectbox("Fixture base dir", [*options, custom_label])
    if selected == custom_label:
        selected = st.text_input(
            "Custom fixture base dir",
            value=str((ROOT / "tests" / "fixtures").resolve()),
        )
    st.caption(selected)
    return selected


def _fixture_dir_candidates() -> list[Path]:
    preferred = [
        ROOT / "tests" / "fixtures",
        ROOT / "tests",
        ROOT / "examples",
        ROOT,
    ]
    candidates: list[Path] = []
    for path in preferred:
        resolved = path.resolve()
        if resolved not in candidates:
            candidates.append(resolved)
    return candidates


def _selected_dataset_name(
    selected_function: str,
    selected_catalog: list[dict[str, Any]],
) -> str:
    if selected_function == "call":
        return "AirKorea raw call"
    dataset_names = sorted(
        {
            str(row["dataset_name"])
            for row in selected_catalog
            if row.get("dataset_name")
        }
    )
    if len(dataset_names) == 1:
        return dataset_names[0]
    if dataset_names:
        return f"{selected_function} ({len(dataset_names)} datasets)"
    return selected_function


def _api_full_name(selected_function: str, catalog_rows: list[dict[str, Any]]) -> str:
    if selected_function == "call":
        return "AirKoreaClient.call"
    if not catalog_rows:
        return selected_function
    return "\n".join(
        f"{row['dataset_name']} / {row['service_name']} / {row['endpoint']}"
        for row in catalog_rows
    )


def _call_catalog_for_input(
    input_data: dict[str, Any],
    catalog_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    service_name = input_data.get("service_name")
    endpoint = input_data.get("endpoint")
    if not isinstance(service_name, str) or not isinstance(endpoint, str):
        return []
    return [
        row
        for row in catalog_rows
        if row["service_name"] == service_name and row["endpoint"] == endpoint
    ]


def _method_options(catalog_rows: list[dict[str, Any]]) -> list[str]:
    methods = {
        method
        for row in catalog_rows
        for method in row["method_names"]
        if method in DEBUGGABLE_METHODS
    }
    methods.add("call")
    return sorted(methods)


def _catalog_for_method(
    catalog_rows: list[dict[str, Any]],
    method_name: str,
) -> list[dict[str, Any]]:
    if method_name == "call":
        return catalog_rows
    return [row for row in catalog_rows if method_name in row["method_names"]]


def _service_key_links(catalog_rows: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for row in catalog_rows:
        url = row.get("service_key_url")
        label = row.get("dataset_name") or row.get("service_label") or "서비스키 링크"
        if not isinstance(url, str) or url in seen:
            continue
        seen.add(url)
        st.link_button(f"서비스키 신청/확인: {label}", url)


def _default_call_params(endpoint: str) -> dict[str, Any]:
    defaults = {
        "getMsrstnList": {"addr": "서울"},
        "getMsrstnAcctoRltmMesureDnsty": {
            "stationName": "종로구",
            "dataTerm": "DAILY",
            "ver": "1.3",
        },
        "getCtprvnRltmMesureDnsty": {"sidoName": "서울", "ver": "1.3"},
        "getNearbyMsrstnList": {"tmX": 198242, "tmY": 451580},
        "getTMStdrCrdnt": {"umdName": "혜화동"},
    }
    return defaults.get(endpoint, {})


if __name__ == "__main__":
    main()
