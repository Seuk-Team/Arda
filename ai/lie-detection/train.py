"""
X.npy / y.npy 로 거짓말 탐지 분류 모델 학습 후 model.pkl 저장.

여러 모델 비교 후 가장 좋은 것 저장.
"""

import numpy as np
import pickle
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.svm import SVC
from sklearn.neural_network import MLPClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.pipeline import Pipeline

X = np.load("processed/X.npy")
y = np.load("processed/y.npy")
print(f"데이터: X={X.shape}, 거짓={y.sum()}, 진실={len(y)-y.sum()}")

cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

models = {
    "SVM (RBF)":    SVC(kernel="rbf", C=1.0, probability=True),
    "MLP":          MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=500, random_state=42),
    "RandomForest": RandomForestClassifier(n_estimators=200, random_state=42),
    "GradBoost":    GradientBoostingClassifier(n_estimators=200, random_state=42),
}

best_name, best_score, best_pipe = None, 0, None

for name, clf in models.items():
    pipe = Pipeline([("scaler", StandardScaler()), ("clf", clf)])
    scores = cross_val_score(pipe, X, y, cv=cv, scoring="accuracy")
    mean, std = scores.mean(), scores.std()
    print(f"  {name:20s}: {mean:.3f} ± {std:.3f}")
    if mean > best_score:
        best_score, best_name, best_pipe = mean, name, pipe

print(f"\n최고 모델: {best_name} ({best_score:.3f})")
best_pipe.fit(X, y)
pickle.dump(best_pipe, open("model.pkl", "wb"))
print("model.pkl 저장 완료")
