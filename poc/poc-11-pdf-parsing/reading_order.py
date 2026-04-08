"""Reading order detection — column layout analysis and text box sorting.

Phase 3: After layout analysis, determine the natural reading order
across columns. Critical for two-column résumés where naive top-to-bottom
sorting produces interleaved nonsense.

RAGFlow uses K-Means with silhouette score to auto-detect column count,
then sorts within each column top-to-bottom. This POC does the same
but with a simplified implementation.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from config import COLUMN_SILHOUETTE_THRESHOLD
from models import TextBox

logger = logging.getLogger(__name__)


def detect_columns(
    text_boxes: list[TextBox],
    page_width: float,
    max_columns: int = 4,
) -> int:
    """Auto-detect the number of text columns using K-Means clustering.

    Clusters text box center-x positions. Uses silhouette score to
    select the best k (number of columns).

    Returns:
        Number of columns detected (1 if single-column or uncertain).
    """
    if len(text_boxes) < 4:
        return 1

    # Collect center-x positions of non-header/footer boxes
    centers = []
    for box in text_boxes:
        if box.layout_type.value in ("header", "footer"):
            continue
        centers.append(box.bbox.center_x)

    if len(centers) < 4:
        return 1

    X = np.array(centers).reshape(-1, 1)

    best_k = 1
    best_score = -1.0

    for k in range(2, min(max_columns + 1, len(centers))):
        try:
            from sklearn.cluster import KMeans
            from sklearn.metrics import silhouette_score

            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(X)

            # Check cluster sizes — reject if any cluster is too small
            unique, counts = np.unique(labels, return_counts=True)
            if min(counts) < 2:
                continue

            score = silhouette_score(X, labels)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            continue

    if best_score < COLUMN_SILHOUETTE_THRESHOLD:
        return 1

    logger.debug("Detected %d columns (silhouette=%.3f)", best_k, best_score)
    return best_k


def assign_columns(
    text_boxes: list[TextBox],
    page_width: float,
    num_columns: int,
) -> list[TextBox]:
    """Assign each text box to a column based on its center-x position.

    For single-column documents, all boxes get column_id=0.
    For multi-column, uses equal-width bins or K-Means centroids.
    """
    if num_columns <= 1:
        for box in text_boxes:
            box.column_id = 0
        return text_boxes

    # Use K-Means to find column boundaries
    centers = []
    body_boxes = []
    for box in text_boxes:
        if box.layout_type.value not in ("header", "footer"):
            centers.append(box.bbox.center_x)
            body_boxes.append(box)

    if not centers:
        return text_boxes

    X = np.array(centers).reshape(-1, 1)

    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=num_columns, n_init=10, random_state=42)
        labels = km.fit_predict(X)

        # Sort cluster centers left-to-right
        center_order = np.argsort(km.cluster_centers_.flatten())
        label_to_col = {original: rank for rank, original in enumerate(center_order)}

        for box, label in zip(body_boxes, labels):
            box.column_id = label_to_col[label]

    except Exception:
        # Fallback: equal-width bins
        col_width = page_width / num_columns
        for box in body_boxes:
            col = int(box.bbox.center_x / col_width)
            box.column_id = min(col, num_columns - 1)

    # Headers/footers span all columns → column_id = -1 (sort first)
    for box in text_boxes:
        if box.layout_type.value in ("header", "footer"):
            box.column_id = -1

    return text_boxes


def sort_reading_order(text_boxes: list[TextBox]) -> list[TextBox]:
    """Sort text boxes in natural reading order.

    Order: headers first → column 0 top-to-bottom → column 1 → ... → footers last.

    Within each column, boxes are sorted by vertical position (y0).
    For boxes at the same vertical position, sort left-to-right (x0).
    """
    def sort_key(box: TextBox) -> tuple:
        # Headers first (column_id = -1), then by column, then by y, then by x
        if box.layout_type.value == "footer":
            group = 2  # Footers last
        elif box.layout_type.value == "header":
            group = 0  # Headers first
        else:
            group = 1  # Body in the middle

        return (
            group,
            box.column_id,
            round(box.bbox.y0, 1),  # Round to avoid float jitter
            box.bbox.x0,
        )

    return sorted(text_boxes, key=sort_key)


def merge_adjacent_boxes(
    text_boxes: list[TextBox],
    y_tolerance: float = 3.0,
    x_gap_max: float = 15.0,
) -> list[TextBox]:
    """Merge horizontally adjacent text boxes on the same line.

    Two boxes merge if they're on the same line (y-overlap) and
    close horizontally (gap < x_gap_max).
    """
    if len(text_boxes) <= 1:
        return text_boxes

    merged: list[TextBox] = []
    current = text_boxes[0].model_copy(deep=True)

    for box in text_boxes[1:]:
        # Same line? (significant y-overlap)
        y_overlap = (min(current.bbox.y1, box.bbox.y1)
                     - max(current.bbox.y0, box.bbox.y0))
        current_height = current.bbox.height
        box_height = box.bbox.height
        min_height = min(current_height, box_height) if min(current_height, box_height) > 0 else 1

        same_line = y_overlap / min_height > 0.5 if min_height > 0 else False

        # Close horizontally?
        x_gap = box.bbox.x0 - current.bbox.x1

        # Same column?
        same_col = current.column_id == box.column_id

        if same_line and same_col and 0 <= x_gap <= x_gap_max:
            # Merge: extend current box
            current.text = current.text + " " + box.text
            current.bbox.x1 = box.bbox.x1
            current.bbox.y0 = min(current.bbox.y0, box.bbox.y0)
            current.bbox.y1 = max(current.bbox.y1, box.bbox.y1)
        else:
            if current.text.strip():
                merged.append(current)
            current = box.model_copy(deep=True)

    if current.text.strip():
        merged.append(current)

    return merged
