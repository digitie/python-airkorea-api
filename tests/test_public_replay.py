"""공개 단일행 재해석이 기존 HTTP DTO와 의미를 공유한다."""

from copy import deepcopy
from datetime import timedelta

import pytest

from airkorea import AirKoreaClient, AirKoreaParseError, parse_measurement
from tests.conftest import FakeResponse, FakeSession, payload
from tests.test_client import measurement_row


async def test_replay_equals_http_dto_and_preserves_source_without_request() -> None:
    raw = measurement_row()
    raw["providerExtra"] = {"unknown": "original"}
    before = deepcopy(raw)
    session = FakeSession([FakeResponse(json_data=payload([raw]))])
    client = AirKoreaClient(service_key="fixture-key", session=session, retries=0)
    original = (await client.station_measurements("종로구"))[0]
    count = len(session.calls)
    replay = parse_measurement(raw)
    assert replay == original
    assert replay.raw == before and raw == before
    assert replay.data_time is not None
    assert replay.data_time.utcoffset() == timedelta(hours=9)
    assert len(session.calls) == count


@pytest.mark.parametrize("missing", ["-", "", "null", "none", "nan", None])
def test_missing_value_is_not_zero_and_station_context_is_supported(missing) -> None:
    raw = {"dataTime": "2026-10-23 10:00", "pm10Value": missing}
    replay = parse_measurement(raw, station_name="측정소001")
    assert replay.station_name == "측정소001" and replay.pm10_value is None
    assert replay.raw == raw


def test_missing_station_keeps_existing_parse_error() -> None:
    with pytest.raises(AirKoreaParseError):
        parse_measurement({"dataTime": "2026-10-23 10:00"})
