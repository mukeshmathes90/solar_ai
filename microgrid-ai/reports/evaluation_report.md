# Microgrid model evaluation

Generated 2026-10-18T08:56:17

> All numbers below are recomputed from predictions on the **held-out
> chronological test set** (`1800` rows) that no model was fitted on.

> The training data is **simulated**. These figures characterise the
> software pipeline, not proven field accuracy on real hardware.

## 1. Split

| Split | Rows |
| --- | --- |
| Train | 8400 |
| Validation | 1800 |
| Test | 1800 |

Strategy: chronological_70_15_15

## 2. Generation regressor (RandomForestRegressor)

Target: total estimated power (W)

| Metric | Value |
| --- | --- |
| MAE | 0.0147 W |
| RMSE | 0.0251 W |
| R2 | 0.9968 |
| Max absolute error | 0.2018 W |

Fraction of predictions inside a tolerance band:

| Band | Share |
| --- | --- |
| +/- 0.05 W | 94.3% |
| +/- 0.10 W | 99.1% |
| +/- 0.25 W | 100.0% |

## 3. Operating-condition classifier (RandomForestClassifier)

Target: `normal` / `reduced_generation` / `night_idle` / `fault`

| Metric | Value |
| --- | --- |
| Accuracy | 0.8528 |
| Macro precision | 0.8646 |
| Macro recall | 0.8153 |
| Macro F1 | 0.8365 |

Per class:

| Class | Precision | Recall | F1 | Support |
| --- | --- | --- | --- | --- |
| fault | 0.953 | 0.795 | 0.867 | 127 |
| night_idle | 0.976 | 1.000 | 0.988 | 82 |
| normal | 0.878 | 0.933 | 0.904 | 1261 |
| reduced_generation | 0.652 | 0.533 | 0.587 | 330 |

Confusion matrix (rows = actual, columns = predicted):

```
                predicted
actual            fault      night_idle          normal  reduced_generation
fault                    101               1              13              12
night_idle                 0              82               0               0
normal                     2               1            1176              82
reduced_generation             3               0             151             176
```

## 4. Anomaly detector (RandomForestClassifier)

| Metric | Value |
| --- | --- |
| Accuracy | 0.9861 |
| Precision | 0.9636 |
| Recall | 0.8346 |
| F1 | 0.8945 |
| Specificity | 0.9976 |

| | Count |
| --- | --- |
| True positives | 106 |
| False positives | 4 |
| False negatives | 21 |
| True negatives | 1669 |

## 5. Limitations

- Trained exclusively on simulated data; real field accuracy is unknown.
- Synthetic faults are cleanly separable, so measured F1 overstates what a real noisy sensor stream would achieve.
- Estimated currents come from the same simulation model as the targets, so the regression task is easier than a real one.
- No battery state-of-charge, no cloud forecast and no tariff signal are modelled; the optimiser is a rule-based demonstration.

## 6. Charts

- `actual_vs_predicted_heldout.png`
- `confusion_matrix_anomaly.png`
- `confusion_matrix_condition.png`
- `feature_importance.png`
- `generation_trend_forecast.png`
- `light_vs_solar_generation.png`
- `model_score_comparison.png`
- `normal_vs_anomalous_patterns.png`
- `operating_condition_distribution.png`
- `regression_evaluation.png`
- `rpm_vs_wind_generation.png`
- `solar_voltage_power_over_time.png`
- `solar_vs_wind_contribution.png`
- `wind_voltage_rpm_over_time.png`
