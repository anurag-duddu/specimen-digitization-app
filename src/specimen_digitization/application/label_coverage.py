"""The automatic label-coverage check (docs/execution/golive/LANE.md T3b, G15).

Deterministic and model-free: it reads the label regions and the cross-check
detections the run already holds from SAM 3. Boxes are (x, y, width, height) in
original pixel edges. The rule's values come from the profile, and the owner
signs off the final values once the acceptance lab has measured them.
"""

from __future__ import annotations

from fractions import Fraction

from .collection_profiles import CoverageRule
from .domain import now
from .image_quality import RegionBox, check_regions

VERSION = "coverage-check-v1"


def area(box):
    return box[2] * box[3]


def intersection_over_union(a, b):
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return 0.0
    overlap = width * height
    return overlap / (area(a) + area(b) - overlap)


def merged_groups(boxes, same):
    """The boxes' groups (lists of indices, in box order): boxes for which
    `same(a, b)` holds, transitively, are one group."""
    parents = list(range(len(boxes)))

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for i, first in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            if same(first, boxes[j]):
                parents[root(i)] = root(j)
    groups = {}
    for index in range(len(boxes)):
        groups.setdefault(root(index), []).append(index)
    return list(groups.values())


def merged_count(boxes, threshold):
    """Boxes overlapping at IoU >= threshold, transitively, count as one label."""
    return len(
        merged_groups(
            boxes, lambda a, b: intersection_over_union(a, b) >= threshold
        )
    )


def nested_duplicate(a, b, rule) -> bool:
    """Whether two boxes are one label boxed twice, one inside the other: at
    least rule.min_containment of the smaller box's area inside the larger,
    and IoU at least rule.min_iou. Exact (integer areas against the values as
    written, no float rounding); a pair exactly at a value meets it."""
    width = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    height = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    if width <= 0 or height <= 0:
        return False
    overlap = width * height
    union = area(a) + area(b) - overlap
    return overlap >= Fraction(str(rule.min_containment)) * min(
        area(a), area(b)
    ) and overlap >= Fraction(str(rule.min_iou)) * union


def covered_fraction(box, cover):
    """The exact share of a box's area inside the union of the cover boxes."""
    if not area(box):
        return 0.0
    x0, y0, x1, y1 = box[0], box[1], box[0] + box[2], box[1] + box[3]
    clipped = [
        (max(x0, c[0]), max(y0, c[1]), min(x1, c[0] + c[2]), min(y1, c[1] + c[3]))
        for c in cover
    ]
    clipped = [c for c in clipped if c[0] < c[2] and c[1] < c[3]]
    edges = sorted({value for c in clipped for value in (c[0], c[2])})
    inside = 0
    for left, right in zip(edges, edges[1:]):
        spans = sorted((c[1], c[3]) for c in clipped if c[0] <= left and right <= c[2])
        length, start, end = 0, None, None
        for low, high in spans:
            if end is None or low > end:
                if end is not None:
                    length += end - start
                start, end = low, high
            else:
                end = max(end, high)
        if end is not None:
            length += end - start
        inside += (right - left) * length
    return inside / area(box)


def too_thin(region, image_width, image_height, fraction) -> bool:
    """Whether a region's shorter side is under the fraction of the image's.

    Exact (the fraction as written, no float rounding); a region exactly at
    the fraction is counted, since the rule is "under".
    """
    if fraction is None:
        return False
    return min(region.width, region.height) < Fraction(str(fraction)) * min(
        image_width, image_height
    )


def check_coverage(rule: CoverageRule, specimen) -> None:
    """Set the run's coverage from the rule and record the evidence (S5's shape)."""
    run, asset = specimen.run, specimen.asset
    labels = [(r.x, r.y, r.width, r.height) for r in run.regions]
    geometry = check_regions(
        asset.width,
        asset.height,
        tuple(
            RegionBox(id=r.id, x=r.x, y=r.y, width=r.width, height=r.height)
            for r in run.regions
        ),
        asset.sha256,
    )
    cross = run.segmentation.get("cross_check") or {}
    counted = [
        detection
        for detection in cross.get("detections", [])
        if detection["score"] >= rule.cross_check_threshold
    ]
    uncovered = [
        detection["box"]
        for detection in counted
        if covered_fraction(detection["box"], labels) < rule.min_inside_fraction
    ]
    fraction = rule.min_region_short_side_fraction
    # A region too thin to hold a label is not counted (count only: the
    # geometry issues and the cross-check above still see every region).
    thin, kept = [], []
    for r in run.regions:
        (thin if too_thin(r, asset.width, asset.height, fraction) else kept).append(r)
    nested = rule.nested_duplicate

    def same(a, b):
        return intersection_over_union(a, b) >= rule.merge_iou or (
            nested is not None and nested_duplicate(a, b, nested)
        )

    groups = merged_groups([(r.x, r.y, r.width, r.height) for r in kept], same)
    region_count = len(groups)
    reasons = [
        issue
        for issue in geometry.issues
        if issue in {"zero_regions", "region_out_of_bounds"}
    ]
    if not rule.min_label_regions <= region_count <= rule.max_label_regions:
        reasons.append("label_region_count_out_of_range")
    if uncovered:
        reasons.append("cross_check_detection_outside_labels")
    run.coverage_confirmed = not reasons
    run.coverage_check = {
        "version": VERSION,
        "outcome": "unconfirmed" if reasons else "confirmed",
        "region_count": region_count,
        # The rule's range, so the record explains itself (S5's thread detail).
        "min_label_regions": rule.min_label_regions,
        "max_label_regions": rule.max_label_regions,
        "cross_check": {
            "concept": cross.get("concept"),
            "threshold": rule.cross_check_threshold,
            "min_inside_fraction": rule.min_inside_fraction,
            "counted": len(counted),
            "uncovered_boxes": uncovered,
        },
        "reason_codes": ["label_coverage_unconfirmed", *reasons] if reasons else [],
        # Present only under a rule with the fraction: the regions too thin to
        # hold a label, which the count left out (they stay in run.regions).
        **(
            {
                "min_region_short_side_fraction": fraction,
                "not_counted_regions": [
                    {"id": r.id, "box": [r.x, r.y, r.width, r.height]} for r in thin
                ],
            }
            if fraction is not None
            else {}
        ),
        # Present only under a rule with the nested-duplicate value: the values
        # used, and each group of regions counted as one label (they stay in
        # run.regions).
        **(
            {
                "nested_duplicate": nested.model_dump(mode="json"),
                "merged_regions": [
                    [kept[index].id for index in group]
                    for group in groups
                    if len(group) > 1
                ],
            }
            if nested is not None
            else {}
        ),
        "evidence_ref": run.segmentation.get("blob_ref"),
        "evidence_sha256": run.segmentation.get("sha256"),
        "checked_at": now(),
    }


def check_run(specimen) -> None:
    """The segment step's check, when the run's profile pins a coverage rule."""
    settings = specimen.run.profile_rules.get("segmentation_settings") or {}
    if settings.get("coverage"):
        check_coverage(CoverageRule.model_validate(settings["coverage"]), specimen)
