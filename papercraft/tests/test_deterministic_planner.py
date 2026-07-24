from papercraft.models.paper_analysis import ExperimentResult
from papercraft.models.paper_analysis import Experiment
from papercraft.planning.deterministic_planner import (
    _comparison_chart_data,
    _primary_experiments,
)


def test_comparison_chart_uses_baseline_score_instead_of_leading_delta():
    result = ExperimentResult(
        result_id="res_example",
        metric="Average Dice (%)",
        value="89.20",
        comparison=(
            "SAA; 0.57 points above the strongest recent SSDG baseline, "
            "SLAug at 88.63."
        ),
        source_refs=["src_example"],
    )

    chart = _comparison_chart_data([result])

    assert [item.value for item in chart] == [88.63, 89.2]


def test_primary_experiments_keep_four_parallel_benchmark_transfers():
    experiments = [
        Experiment(
            experiment_id=f"exp_transfer_{index}",
            question=f"Main benchmark comparison {index}",
            setup="Matched benchmark comparison.",
            datasets=["source", "target"],
            metrics=["Dice"],
            baselines=["baseline"],
            results=[
                ExperimentResult(
                    result_id=f"res_transfer_{index}",
                    metric="Dice",
                    value=str(80 + index),
                    comparison=f"Baseline at {79 + index}.",
                    source_refs=[f"src_{index}"],
                )
            ],
            source_refs=[f"src_{index}"],
        )
        for index in range(1, 6)
    ]

    selected = _primary_experiments(experiments)

    assert len(selected) == 4


def test_comparison_chart_keeps_parallel_transfer_rows_distinct():
    results = [
        ExperimentResult(
            result_id=f"res_{direction}_saa_average",
            metric="Average Dice (%)",
            value=value,
            comparison=f"Baseline at {baseline}.",
            source_refs=[f"src_{direction}"],
        )
        for direction, value, baseline in (
            ("ct_to_mri", "89.20", "88.63"),
            ("mri_to_ct", "85.55", "84.45"),
        )
    ]

    chart = _comparison_chart_data(results)

    assert [chart[0].label, chart[2].label] == ["CT → MRI", "MRI → CT"]
