"""Synthetic timeline playback checks; no research observations or metrics."""

import pandas as pd
import pytest

from src.visualization import job_title_trend, style_chart


def test_title_trend_frames_reveal_observed_counts_and_finish_on_full_data():
    monthly = pd.DataFrame({"month": ["2026-03", "2026-01", "2026-01", "2026-03"],
                            "job_title": ["data analyst", "data analyst", "data engineer", "data engineer"],
                            "job_ads": [3, 1, 2, 0]})
    original = monthly.copy(deep=True)
    fig = job_title_trend(monthly)
    assert [frame.name for frame in fig.frames] == ["2026-01", "2026-02", "2026-03"]
    assert [trace.name for trace in fig.data] == ["data analyst", "data engineer"]
    assert list(fig.data[0].y) == [1, 0, 3]
    assert list(fig.data[1].y) == [2, 0, 0]
    for index, frame in enumerate(fig.frames, 1):
        assert list(frame.traces) == [0, 1]
        assert len(frame.data) == len(fig.data)
        assert all(len(trace.x) == index for trace in frame.data)
    for initial, final in zip(fig.data, fig.frames[-1].data):
        assert list(initial.x) == list(final.x)
        assert list(initial.y) == list(final.y)
    assert fig.layout.yaxis.tickformat == ",d" and fig.layout.yaxis.dtick >= 1
    assert fig.layout.yaxis.range[0] == 0
    assert not any(frame.layout.xaxis.range or frame.layout.yaxis.range for frame in fig.frames)
    pd.testing.assert_frame_equal(monthly, original)


def test_title_trend_playback_restarts_and_slides_without_interpolating_counts():
    fig = job_title_trend(pd.DataFrame({"month": ["2026-01", "2026-02"],
                                       "job_title": ["analyst"] * 2, "job_ads": [1, 3]}))
    play, pause = fig.layout.updatemenus[0].buttons
    assert list(play.args[0]) == ["2026-01", "2026-02"]
    assert play.args[1]["fromcurrent"] is False
    assert play.args[1]["transition"]["duration"] == 0
    assert pause.args[0] == (None,)
    assert fig.layout.sliders[0].active == 1  # Complete data is visible before Play.
    assert all(step.args[1]["transition"]["duration"] == 0 for step in fig.layout.sliders[0].steps)
    styled = style_chart(fig)
    assert styled.layout.legend.y > 1
    assert styled.layout.margin.b >= 150 and styled.layout.height == 490


def test_title_trend_empty_and_invalid_counts_are_explicit():
    empty = job_title_trend(pd.DataFrame())
    assert not empty.data and not empty.frames
    with pytest.raises(ValueError, match="whole advertisement counts"):
        job_title_trend(pd.DataFrame({"month": ["2026-01"], "job_title": ["analyst"], "job_ads": [.5]}))


def test_title_trend_bounds_cumulative_playback_cost_and_keeps_complete_final_series():
    monthly = pd.DataFrame([{"month": month, "job_title": f"title {title}", "job_ads": count}
                            for month, count in (("2000-01", 1), ("2049-12", 2)) for title in range(8)])
    fig = job_title_trend(monthly)
    assert 2 <= len(fig.frames) <= 48
    assert 600 * len(fig.data) * len(fig.frames) <= 120000
    assert fig.frames[0].name == "2000-01" and fig.frames[-1].name == "2049-12"
    assert fig.layout.meta["fow_playback_sampled"] is True
    assert fig.layout.meta["fow_timeline_months"] == 600
    assert fig.layout.meta["fow_playback_steps"] == len(fig.frames)
    assert [step.args[0][0] for step in fig.layout.sliders[0].steps] == [frame.name for frame in fig.frames]
    for initial, final in zip(fig.data, fig.frames[-1].data):
        assert len(initial.x) == len(final.x) == 600
        assert list(initial.y) == list(final.y)
        assert sum(final.y) == 3
