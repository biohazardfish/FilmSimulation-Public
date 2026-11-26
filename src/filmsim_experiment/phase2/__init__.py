"""Phase II physical-fidelity validation utilities.

The package deliberately separates computational checks (V1), published
reference agreement (V2), independent measurements (V3), and matched
end-to-end photography (V4).
"""

from .color_validation import evaluate_color_reference, load_color_reference
from .metrics import curve_metrics, metric_record, monotonicity

__all__ = [
    "curve_metrics",
    "evaluate_color_reference",
    "load_color_reference",
    "metric_record",
    "monotonicity",
]
