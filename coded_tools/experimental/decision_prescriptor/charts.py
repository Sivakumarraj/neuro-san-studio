# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT
"""
Self-contained SVG rendering for a Pareto front.

A trade-off front is one of the few results that genuinely cannot be read as a
table. The shape of the curve is the finding: where it is steep, a small
concession on one objective buys a large gain on another, and where it is flat,
it does not. So the charts here are the output, not decoration on it.

Everything is emitted as inline SVG inside a single HTML file with no external
stylesheet, script or font, which keeps a report readable straight from disk and
matches how the rest of this repo ships visual output.

Colors come from the repo's validated data-visualization palette. Blue and orange
were checked against the colorblind-separation and contrast gates on both the
light and dark surfaces before being used here.
"""

import html
from typing import Dict
from typing import List
from typing import Sequence

import numpy as np

# Palette roles. Light and dark are separately chosen steps, not an inversion.
_THEME = {
    "light": {
        "surface": "#fcfcfb",
        "plane": "#f9f9f7",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series_1": "#2a78d6",
        "series_2": "#eb6834",
        "border": "rgba(11,11,11,0.10)",
    },
    "dark": {
        "surface": "#1a1a19",
        "plane": "#0d0d0d",
        "primary": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series_1": "#3987e5",
        "series_2": "#d95926",
        "border": "rgba(255,255,255,0.10)",
    },
}

_PLOT_WIDTH = 460
_PLOT_HEIGHT = 320
# Full-bleed charts use their own width so they render near 1:1 rather than being
# scaled up from a narrow viewBox, which would enlarge the text along with the plot.
_WIDE_WIDTH = 940
_MARGIN = {"top": 24, "right": 24, "bottom": 52, "left": 72}


def _nice_ticks(low: float, high: float, target_count: int = 5) -> List[float]:
    """
    Choose readable axis tick values covering a range.

    Steps are snapped to 1, 2 or 5 times a power of ten, which is what makes
    axis labels land on round numbers a reader can hold in their head.

    :param low: Lowest value that must be covered.
    :param high: Highest value that must be covered.
    :param target_count: Rough number of ticks wanted.
    :return: Ascending tick values spanning at least [low, high].
    """
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return [low, low + 1.0] if np.isfinite(low) else [0.0, 1.0]

    raw_step = (high - low) / max(target_count, 1)
    magnitude = 10.0 ** np.floor(np.log10(raw_step))
    for multiple in (1.0, 2.0, 5.0, 10.0):
        if raw_step <= multiple * magnitude:
            step = multiple * magnitude
            break

    start = np.floor(low / step) * step
    ticks = []
    value = start
    while value < high + step * 0.5:
        # Snap away floating point dust so labels read as round numbers.
        ticks.append(float(round(value, 10)))
        value += step
    return ticks


def _format_number(value: float) -> str:
    """
    Format a number compactly for an axis label or tooltip.

    :param value: Number to format.
    :return: Short human-readable string.
    """
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:.1f}k"
    if magnitude >= 10:
        return f"{value:.1f}"
    if magnitude >= 0.01:
        return f"{value:.3g}"
    return f"{value:.2e}"


# A scale is a callable with one job; splitting it further would not help a reader.
# pylint: disable=too-few-public-methods
class _LinearScale:
    """
    Maps a data range onto a pixel range.
    """

    def __init__(self, domain_low: float, domain_high: float, range_low: float, range_high: float):
        """
        :param domain_low: Lowest data value.
        :param domain_high: Highest data value.
        :param range_low: Pixel position for domain_low.
        :param range_high: Pixel position for domain_high.
        """
        # A degenerate domain would divide by zero; widen it symmetrically instead.
        if domain_high - domain_low < 1e-12:
            padding = max(abs(domain_low) * 0.05, 0.5)
            domain_low, domain_high = domain_low - padding, domain_high + padding
        self.domain_low = domain_low
        self.domain_high = domain_high
        self.range_low = range_low
        self.range_high = range_high

    def __call__(self, value: float) -> float:
        """
        :param value: Data value to place.
        :return: Pixel position.
        """
        fraction = (value - self.domain_low) / (self.domain_high - self.domain_low)
        return self.range_low + fraction * (self.range_high - self.range_low)


# pylint: disable=too-many-arguments,too-many-positional-arguments
def _axes(
    x_scale: _LinearScale,
    y_scale: _LinearScale,
    x_label: str,
    y_label: str,
    width: int,
    height: int,
) -> str:
    """
    Render recessive gridlines, ticks and axis titles.

    :param x_scale: Horizontal scale.
    :param y_scale: Vertical scale.
    :param x_label: Title under the horizontal axis.
    :param y_label: Title beside the vertical axis.
    :param width: Full SVG width.
    :param height: Full SVG height.
    :return: SVG fragment.
    """
    parts: List[str] = []
    plot_left = _MARGIN["left"]
    plot_right = width - _MARGIN["right"]
    plot_top = _MARGIN["top"]
    plot_bottom = height - _MARGIN["bottom"]

    for tick in _nice_ticks(y_scale.domain_low, y_scale.domain_high):
        position = y_scale(tick)
        if not plot_top - 1 <= position <= plot_bottom + 1:
            continue
        parts.append(
            f'<line x1="{plot_left}" y1="{position:.1f}" x2="{plot_right}" y2="{position:.1f}" class="grid"/>'
        )
        parts.append(
            f'<text x="{plot_left - 10}" y="{position + 4:.1f}" class="tick" text-anchor="end">'
            f"{html.escape(_format_number(tick))}</text>"
        )

    for tick in _nice_ticks(x_scale.domain_low, x_scale.domain_high):
        position = x_scale(tick)
        if not plot_left - 1 <= position <= plot_right + 1:
            continue
        parts.append(
            f'<line x1="{position:.1f}" y1="{plot_top}" x2="{position:.1f}" y2="{plot_bottom}" class="grid"/>'
        )
        parts.append(
            f'<text x="{position:.1f}" y="{plot_bottom + 20}" class="tick" text-anchor="middle">'
            f"{html.escape(_format_number(tick))}</text>"
        )

    parts.append(f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" class="axis"/>')
    parts.append(f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}" class="axis"/>')

    parts.append(
        f'<text x="{(plot_left + plot_right) / 2:.1f}" y="{height - 8}" class="axis-title" '
        f'text-anchor="middle">{html.escape(x_label)}</text>'
    )
    parts.append(
        f'<text x="16" y="{(plot_top + plot_bottom) / 2:.1f}" class="axis-title" text-anchor="middle" '
        f'transform="rotate(-90 16 {(plot_top + plot_bottom) / 2:.1f})">{html.escape(y_label)}</text>'
    )
    return "".join(parts)


# Chart builders name every axis, label and series they draw; bundling them into a
# config object would hide the signature without simplifying the drawing.
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
def pareto_scatter_svg(
    front: np.ndarray,
    dominated: np.ndarray,
    x_index: int,
    y_index: int,
    labels: Sequence[str],
    connect: bool = False,
) -> str:
    """
    Scatter one pair of objectives, front against dominated solutions.

    Dominated points stay in a neutral ink rather than a second series color:
    they are context, not a category worth competing for attention. Front points
    carry a surface-colored ring so overlapping markers remain countable.

    The connecting line is opt-in and correct only for a genuinely two-objective
    problem, where the front really is a monotone curve. With three or more
    objectives this chart is a projection: two strategies adjacent here can be far
    apart on the objective that is not shown, so joining them would draw a
    relationship that does not exist.

    :param front: Non-dominated objectives, shape (num_front, num_objectives).
    :param dominated: Dominated objectives, shape (num_dominated, num_objectives).
    :param x_index: Objective plotted horizontally.
    :param y_index: Objective plotted vertically.
    :param labels: Display name per objective.
    :param connect: Whether to join front points into a curve.
    :return: A complete <svg> element.
    """
    width, height = _PLOT_WIDTH, _PLOT_HEIGHT
    everything = np.vstack([front, dominated]) if dominated.size else front

    x_values, y_values = everything[:, x_index], everything[:, y_index]
    x_pad = (x_values.max() - x_values.min()) * 0.08 or 0.5
    y_pad = (y_values.max() - y_values.min()) * 0.08 or 0.5

    x_scale = _LinearScale(x_values.min() - x_pad, x_values.max() + x_pad, _MARGIN["left"], width - _MARGIN["right"])
    y_scale = _LinearScale(y_values.min() - y_pad, y_values.max() + y_pad, height - _MARGIN["bottom"], _MARGIN["top"])

    parts = [_axes(x_scale, y_scale, labels[x_index], labels[y_index], width, height)]

    for row in dominated:
        parts.append(
            f'<circle cx="{x_scale(row[x_index]):.1f}" cy="{y_scale(row[y_index]):.1f}" r="3.5" '
            f'class="dominated"><title>dominated — {html.escape(labels[x_index])} '
            f"{_format_number(row[x_index])}, {html.escape(labels[y_index])} "
            f"{_format_number(row[y_index])}</title></circle>"
        )

    # Draw the front last so it is never buried under the cloud of dominated points.
    order = np.argsort(front[:, x_index])
    if connect:
        trace = " ".join(f"{x_scale(front[i, x_index]):.1f},{y_scale(front[i, y_index]):.1f}" for i in order)
        parts.append(f'<polyline points="{trace}" class="front-line"/>')

    for position, index in enumerate(order):
        row = front[index]
        parts.append(
            f'<circle cx="{x_scale(row[x_index]):.1f}" cy="{y_scale(row[y_index]):.1f}" r="5" '
            f'class="front"><title>strategy {position + 1} — {html.escape(labels[x_index])} '
            f"{_format_number(row[x_index])}, {html.escape(labels[y_index])} "
            f"{_format_number(row[y_index])}</title></circle>"
        )

    return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">{"".join(parts)}</svg>'


# pylint: disable=too-many-locals
def parallel_coordinates_svg(front: np.ndarray, labels: Sequence[str], highlight: int = None) -> str:
    """
    Show every front solution as a line across all objectives at once.

    Where the scatter shows one pair, this shows the whole trade-off: a line that
    sits high on one axis and low on the next is a strategy making exactly that
    exchange. Each axis is normalized to its own range because the objectives are
    in different units.

    :param front: Non-dominated objectives, shape (num_front, num_objectives).
    :param labels: Display name per objective.
    :param highlight: Optional row index drawn in the second series color and labelled.
    :return: A complete <svg> element.
    """
    num_objectives = front.shape[1]
    # Sized close to its rendered width. An SVG scaled up from a small viewBox
    # scales its type with it, which is what turns 12px axis labels into headlines.
    width = max(_WIDE_WIDTH, 220 * num_objectives)
    height = 360

    plot_top = _MARGIN["top"]
    plot_bottom = height - _MARGIN["bottom"]
    axis_x = np.linspace(_MARGIN["left"], width - _MARGIN["right"], num_objectives)

    low = front.min(axis=0)
    high = front.max(axis=0)
    span = np.where((high - low) < 1e-12, 1.0, high - low)

    parts: List[str] = []
    for index, position in enumerate(axis_x):
        # The outermost axes sit on the plot edges, so centred labels would run off
        # the canvas and be clipped. Anchor those two inward instead.
        if index == 0:
            anchor = "start"
        elif index == num_objectives - 1:
            anchor = "end"
        else:
            anchor = "middle"

        parts.append(
            f'<line x1="{position:.1f}" y1="{plot_top}" x2="{position:.1f}" y2="{plot_bottom}" class="axis"/>'
        )
        parts.append(
            f'<text x="{position:.1f}" y="{plot_bottom + 22}" class="axis-title" text-anchor="{anchor}">'
            f"{html.escape(labels[index])}</text>"
        )
        parts.append(
            f'<text x="{position:.1f}" y="{plot_top - 8}" class="tick" text-anchor="{anchor}">'
            f"{html.escape(_format_number(high[index]))}</text>"
        )
        parts.append(
            f'<text x="{position:.1f}" y="{plot_bottom + 38}" class="tick" text-anchor="{anchor}">'
            f"{html.escape(_format_number(low[index]))}</text>"
        )

    def row_points(row: np.ndarray) -> str:
        normalized = (row - low) / span
        return " ".join(
            f"{axis_x[i]:.1f},{plot_bottom - normalized[i] * (plot_bottom - plot_top):.1f}"
            for i in range(num_objectives)
        )

    for index, row in enumerate(front):
        if index == highlight:
            continue
        summary = ", ".join(f"{labels[i]} {_format_number(row[i])}" for i in range(num_objectives))
        parts.append(
            f'<polyline points="{row_points(row)}" class="pc-line">'
            f"<title>strategy {index + 1} — {html.escape(summary)}</title></polyline>"
        )

    if highlight is not None and 0 <= highlight < front.shape[0]:
        row = front[highlight]
        summary = ", ".join(f"{labels[i]} {_format_number(row[i])}" for i in range(num_objectives))
        parts.append(
            f'<polyline points="{row_points(row)}" class="pc-line-highlight">'
            f"<title>balanced pick — {html.escape(summary)}</title></polyline>"
        )
        # Anchored to the line's own right-hand end, clear of the axis maxima
        # printed along the top edge.
        normalized_end = (row[-1] - low[-1]) / span[-1]
        end_y = plot_bottom - normalized_end * (plot_bottom - plot_top)
        parts.append(
            f'<text x="{axis_x[-1] - 8:.1f}" y="{end_y - 10:.1f}" class="direct-label" text-anchor="end">'
            f"balanced pick</text>"
        )

    return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">{"".join(parts)}</svg>'


def convergence_svg(history: Sequence[float]) -> str:
    """
    Plot archived hypervolume against generation.

    This is the run's own evidence that the search made progress. Because the
    archive only ever grows, the curve can only rise; a curve that flattens early
    says the extra generations bought nothing.

    :param history: Hypervolume after each generation.
    :return: A complete <svg> element.
    """
    values = np.asarray(list(history), dtype=float)
    width, height = _WIDE_WIDTH, 260
    if values.size == 0:
        return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart"></svg>'

    generations = np.arange(1, values.size + 1)
    y_pad = (values.max() - values.min()) * 0.1 or 0.5

    x_scale = _LinearScale(1, max(values.size, 2), _MARGIN["left"], width - _MARGIN["right"])
    y_scale = _LinearScale(values.min() - y_pad, values.max() + y_pad, height - _MARGIN["bottom"], _MARGIN["top"])

    parts = [_axes(x_scale, y_scale, "generation", "hypervolume", width, height)]
    trace = " ".join(f"{x_scale(generations[i]):.1f},{y_scale(values[i]):.1f}" for i in range(values.size))
    parts.append(f'<polyline points="{trace}" class="series-line"/>')

    # Direct-label the end point only; a number on every point would be noise.
    parts.append(f'<circle cx="{x_scale(generations[-1]):.1f}" cy="{y_scale(values[-1]):.1f}" r="5" class="front"/>')
    parts.append(
        f'<text x="{x_scale(generations[-1]) - 8:.1f}" y="{y_scale(values[-1]) - 12:.1f}" '
        f'class="direct-label" text-anchor="end">{html.escape(_format_number(values[-1]))}</text>'
    )
    return f'<svg viewBox="0 0 {width} {height}" role="img" class="chart">{"".join(parts)}</svg>'


def _front_table(front: np.ndarray, actions: np.ndarray, labels: Sequence[str], action_labels: Sequence[str]) -> str:
    """
    Render the front as an HTML table.

    The table is the accessibility path for the charts above and the practical way
    to read exact values, so it always ships rather than being an optional extra.

    :param front: Objective values per strategy.
    :param actions: Representative action values per strategy.
    :param labels: Objective display names.
    :param action_labels: Action display names.
    :return: HTML fragment.
    """
    header = "".join(f"<th>{html.escape(name)}</th>" for name in list(labels) + list(action_labels))
    rows = []
    for index in range(front.shape[0]):
        cells = "".join(f"<td>{html.escape(_format_number(value))}</td>" for value in front[index])
        cells += "".join(f"<td>{html.escape(_format_number(value))}</td>" for value in actions[index])
        rows.append(f"<tr><th scope='row'>{index + 1}</th>{cells}</tr>")
    return (
        "<div class='table-wrap'><table><caption>Pareto front — objective values and mean prescribed action"
        f"</caption><thead><tr><th scope='col'>#</th>{header}</tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


_STYLE = """
:root { color-scheme: light dark; }
body { margin: 0; background: var(--plane); color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 1.5rem; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 1rem; margin: 0 0 2px; }
p.sub { color: var(--text-secondary); margin: 0 0 28px; font-size: 0.875rem; line-height: 1.5; }
p.note { color: var(--text-secondary); margin: 0 0 12px; font-size: 0.8125rem; line-height: 1.5; }
section { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  padding: 20px; margin-bottom: 20px; }
.grid-2 { display: grid; gap: 24px; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); }
.chart { width: 100%; height: auto; overflow: visible; display: block; }
.chart-scroll { overflow-x: auto; }
line.grid { stroke: var(--grid); stroke-width: 1; }
line.axis { stroke: var(--axis); stroke-width: 1; }
text.tick { fill: var(--muted); font-size: 11px; }
text.axis-title { fill: var(--text-secondary); font-size: 12px; }
text.direct-label { fill: var(--text-primary); font-size: 12px; font-weight: 600; }
circle.dominated { fill: var(--muted); opacity: 0.42; }
circle.front { fill: var(--series-1); stroke: var(--surface); stroke-width: 2; }
circle.front:hover { r: 7; }
polyline.front-line { fill: none; stroke: var(--series-1); stroke-width: 2; opacity: 0.35; }
polyline.series-line { fill: none; stroke: var(--series-1); stroke-width: 2;
  stroke-linejoin: round; stroke-linecap: round; }
polyline.pc-line { fill: none; stroke: var(--series-1); stroke-width: 1.5; opacity: 0.3; }
polyline.pc-line:hover { opacity: 1; stroke-width: 2.5; }
polyline.pc-line-highlight { fill: none; stroke: var(--series-2); stroke-width: 3; }
.legend { display: flex; gap: 18px; flex-wrap: wrap; margin: 4px 0 14px;
  font-size: 0.8125rem; color: var(--text-secondary); }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.swatch { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.8125rem; }
caption { text-align: left; color: var(--text-secondary); font-size: 0.8125rem; padding-bottom: 10px; }
th, td { padding: 7px 12px; text-align: right; border-bottom: 1px solid var(--grid);
  font-variant-numeric: tabular-nums; }
thead th { color: var(--text-secondary); font-weight: 600; text-align: right; white-space: nowrap; }
tbody th { color: var(--text-secondary); font-weight: 500; text-align: left; }
dl.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 18px; margin: 0; }
dt { color: var(--text-secondary); font-size: 0.75rem; margin-bottom: 4px; }
dd { margin: 0; font-size: 1.375rem; font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
"""


def _theme_variables() -> str:
    """
    Emit the palette as CSS custom properties for both light and dark surfaces.

    Dark is a selected set of steps validated against the dark surface, not an
    automatic inversion of the light values.

    :return: A CSS fragment defining the theme variables under both scopes.
    """

    def block(mode: str) -> str:
        theme = _THEME[mode]
        return (
            f"--surface:{theme['surface']};--plane:{theme['plane']};"
            f"--text-primary:{theme['primary']};--text-secondary:{theme['secondary']};"
            f"--muted:{theme['muted']};--grid:{theme['grid']};--axis:{theme['axis']};"
            f"--series-1:{theme['series_1']};--series-2:{theme['series_2']};--border:{theme['border']};"
        )

    return (
        f":root{{{block('light')}}}"
        f"@media (prefers-color-scheme: dark){{:root:not([data-theme='light']){{{block('dark')}}}}}"
        f":root[data-theme='dark']{{{block('dark')}}}"
    )


# pylint: disable=too-many-arguments,too-many-positional-arguments
def render_report(
    title: str,
    front: np.ndarray,
    dominated: np.ndarray,
    actions: np.ndarray,
    objective_labels: Sequence[str],
    action_labels: Sequence[str],
    hypervolume_history: Sequence[float],
    summary: Dict[str, str],
    balanced_index: int = None,
) -> str:
    """
    Assemble the full HTML report for one prescriptor run.

    :param front: Non-dominated objectives in display orientation, shape (n, num_objectives).
    :param dominated: Dominated objectives in display orientation.
    :param actions: Mean prescribed action per front solution, shape (n, num_actions).
    :param objective_labels: Objective display names.
    :param action_labels: Action display names.
    :param hypervolume_history: Hypervolume after each generation.
    :param summary: Named run facts shown as stat tiles.
    :param balanced_index: Row of `front` to highlight as a balanced compromise.
    :param title: Page heading.
    :return: A complete, self-contained HTML document.
    """
    num_objectives = front.shape[1]

    # Pairwise projections: one chart for two objectives, small multiples beyond that.
    pairs = (
        [(0, 1)]
        if num_objectives == 2
        else [(i, j) for i in range(num_objectives) for j in range(i + 1, num_objectives)]
    )
    scatters = "".join(
        f"<div><h2>{html.escape(objective_labels[i])} vs {html.escape(objective_labels[j])}</h2>"
        f"{pareto_scatter_svg(front, dominated, i, j, objective_labels, connect=num_objectives == 2)}</div>"
        for i, j in pairs
    )

    stat_tiles = "".join(
        f"<div><dt>{html.escape(key)}</dt><dd>{html.escape(value)}</dd></div>" for key, value in summary.items()
    )

    legend = (
        "<div class='legend'>"
        "<span><i class='swatch' style='background:var(--series-1)'></i>Pareto front</span>"
        "<span><i class='swatch' style='background:var(--muted);opacity:.45'></i>dominated</span>"
        "</div>"
    )
    pc_legend = (
        "<div class='legend'>"
        "<span><i class='swatch' style='background:var(--series-1)'></i>front strategies</span>"
        "<span><i class='swatch' style='background:var(--series-2)'></i>balanced pick</span>"
        "</div>"
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_theme_variables()}{_STYLE}</style></head>
<body><div class="wrap">
<h1>{html.escape(title)}</h1>
<p class="sub">Each point is a distinct strategy that nothing else beats on every objective at once.
Moving along the front always means giving something up — that exchange is the decision.</p>
<section><dl class="stats">{stat_tiles}</dl></section>
<section><h2>Trade-off front</h2>
<p class="note">Grey points were reached during the search but are beaten outright on every objective,
so they are never worth choosing.</p>
{legend}<div class="grid-2">{scatters}</div></section>
<section><h2>Strategies across all objectives</h2>
<p class="note">One line per strategy. A line that rises on one axis and falls on the next is making
exactly that trade.</p>
{pc_legend}<div class="chart-scroll">{parallel_coordinates_svg(front, objective_labels, balanced_index)}</div>
</section>
<section><h2>Search progress</h2>
<p class="note">Hypervolume of the archived front after each generation. It rises by construction, so a
flat tail means further generations added nothing.</p>
{convergence_svg(hypervolume_history)}</section>
<section><h2>The numbers</h2>{_front_table(front, actions, objective_labels, action_labels)}</section>
</div></body></html>"""
