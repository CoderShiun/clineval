"""Module B placeholder: report-generation evaluation.

Intentionally empty for the MVP. A future task adds report-generation metrics
(faithfulness / hallucination) here, registered under task name
"report_generation", reusing the same core schema, evaluator, and metric
registry — without touching Module A. The report layer is not a drop-in reuse:
each task configures it with its own template and metric set.
"""
