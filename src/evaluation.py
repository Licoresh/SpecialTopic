import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_score, recall_score, f1_score

def evaluate_model(model, x_test, y_test):
    predicted = model.predict(x_test)
    labels = list(model.classes_)
    metrics = {"accuracy": float(accuracy_score(y_test, predicted))}
    for average in ("macro", "weighted"):
        p = precision_score(y_test, predicted, average=average, zero_division=0)
        r = recall_score(y_test, predicted, average=average, zero_division=0)
        f = f1_score(y_test, predicted, average=average, zero_division=0)
        metrics.update({f"{average}_precision": float(p), f"{average}_recall": float(r), f"{average}_f1": float(f)})
    report = pd.DataFrame(classification_report(y_test, predicted, labels=labels, output_dict=True, zero_division=0)).T.loc[labels]
    matrix = pd.DataFrame(confusion_matrix(y_test, predicted, labels=labels), index=labels, columns=labels)
    confidence = model.predict_proba(x_test).max(axis=1) if hasattr(model, "predict_proba") else [None]*len(predicted)
    return {"metrics": metrics, "per_class": report, "confusion": matrix,
            "predictions": pd.DataFrame({"phrase": list(x_test), "actual": list(y_test), "predicted": predicted,
                                         "true_label": list(y_test), "predicted_label": predicted, "confidence": confidence,
                                         "correct": [actual == prediction for actual,prediction in zip(y_test, predicted)]})}
