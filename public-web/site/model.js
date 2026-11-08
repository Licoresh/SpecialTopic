const word = String.raw`[\p{L}\p{N}_]`;
const tokenPattern = new RegExp(String.raw`(?<!${word})(?:\.net|c\+\+|c#|${word}+)(?!${word})`, "gu");

export function browserClassifier(model) {
  const {schema, version, name, trainedAt, kind, classes, terms, idf, weights, intercepts, casefold,
    releaseStatus, releaseNote} = model;
  if (schema !== 1 || !/^[0-9a-f]{16}$/.test(version) || typeof name !== "string"
      || !Number.isFinite(Date.parse(trainedAt)) || !["logistic", "multinomial_nb"].includes(kind)
      || !Array.isArray(classes) || classes.length < 2 || classes.length > 8 || !classes.every(label => typeof label === "string")
      || !Array.isArray(terms) || !terms.length || terms.length > 100000 || !terms.every(term => typeof term === "string")
      || !Array.isArray(idf) || idf.length !== terms.length || !idf.every(value => Number.isFinite(value) && value > 0)
      || !casefold || typeof casefold !== "object") {
    throw new Error("Unsupported public classifier.");
  }
  const binary = kind === "logistic" && classes.length === 2;
  const scoreCount = binary ? 1 : classes.length;
  if (!Array.isArray(weights) || weights.length !== scoreCount || !weights.every(row => Array.isArray(row)
      && row.length === terms.length && row.every(Number.isFinite)) || !Array.isArray(intercepts)
      || intercepts.length !== scoreCount || !intercepts.every(Number.isFinite)) {
    throw new Error("Invalid public classifier weights.");
  }
  const indices = new Map(terms.map((term, index) => [term, index]));
  const folds = new Map(Object.entries(casefold));
  return {
    version, name, trainedAt, releaseStatus: releaseStatus || "approved", releaseNote: releaseNote || "",
    predict(phrase) {
      const text = Array.from(phrase.normalize("NFKC"), char => folds.get(char) ?? char.toLowerCase()).join("");
      const tokens = text.match(tokenPattern) ?? [];
      const counts = new Map();
      function count(term) {
        const i = indices.get(term);
        if (i !== undefined) counts.set(i, (counts.get(i) ?? 0) + 1);
      }
      tokens.forEach((token, i) => {
        count(token);
        if (i) count(`${tokens[i - 1]} ${token}`);
      });
      if (!counts.size) return null;
      const features = [...counts].map(([i, frequency]) => [i, (1 + Math.log(frequency)) * idf[i]]);
      const norm = Math.sqrt(features.reduce((sum, [, value]) => sum + value * value, 0));
      const scores = weights.map((row, c) => features.reduce((sum, [i, value]) => sum + row[i] * value / norm, intercepts[c]));
      // Binary LogisticRegression uses a sigmoid. Naive Bayes and multiclass LogisticRegression use softmax.
      if (binary) {
        const positive = scores[0] > 0;
        return {label: classes[Number(positive)], probability: 1 / (1 + Math.exp(-Math.abs(scores[0])))};
      }
      const maximum = Math.max(...scores);
      const sum = scores.reduce((total, score) => total + Math.exp(score - maximum), 0);
      return {label: classes[scores.indexOf(maximum)], probability: 1 / sum};
    },
  };
}

export async function loadClassifier() {
  try {
    const response = await fetch(new URL("./model.json", import.meta.url), {cache: "no-cache", signal: AbortSignal.timeout(5000)});
    if (response.ok) {
      const model = await response.json();
      if (model.schema === 0) return null;
      return browserClassifier(model);
    }
  } catch {
    // The public analyzer can run on its published vocabulary while a release is unavailable.
  }
  return null;
}
