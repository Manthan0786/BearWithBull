from __future__ import annotations

from dataclasses import dataclass

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


@dataclass
class SentimentResult:
    compound: float
    label: str  # STRONG_POSITIVE | STRONG_NEGATIVE | IGNORE


class SentimentScorer:
    """Thin wrapper around VADER sentiment scoring."""

    def __init__(self, threshold: float = 0.70):
        self.analyzer = SentimentIntensityAnalyzer()
        self.threshold = threshold

    def score(self, text: str) -> SentimentResult:
        if not text:
            return SentimentResult(compound=0.0, label="IGNORE")
        vs = self.analyzer.polarity_scores(text)
        compound = float(vs.get("compound", 0.0))
        if compound > self.threshold:
            label = "STRONG_POSITIVE"
        elif compound < -self.threshold:
            label = "STRONG_NEGATIVE"
        else:
            label = "IGNORE"
        return SentimentResult(compound=compound, label=label)

