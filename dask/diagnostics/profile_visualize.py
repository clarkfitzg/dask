from __future__ import division, absolute_import

from itertools import cycle
from operator import itemgetter

from toolz import unique, groupby
import bokeh.plotting as bp
from bokeh.io import _state
from bokeh.palettes import brewer
from bokeh.models import HoverTool, LinearAxis, Range1d

from ..dot import funcname
from ..core import istask


def pprint_task(task, keys, label_size=60):
    """Return a nicely formatted string for a task.

    Parameters
    ----------
    task:
        Value within dask graph to render as text
    keys: iterable
        List of keys within dask graph
    label_size: int (optional)
        Maximum size of output label, defaults to 60

    Examples
    --------
    >>> from operator import add, mul
    >>> dsk = {'a': 1,
    ...        'b': 2,
    ...        'c': (add, 'a', 'b'),
    ...        'd': (add, (mul, 'a', 'b'), 'c'),
    ...        'e': (sum, ['a', 'b', 5])}

    >>> pprint_task(dsk['c'], dsk)
    'add(_, _)'
    >>> pprint_task(dsk['d'], dsk)
    'add(mul(_, _), _)'
    >>> pprint_task(dsk['e'], dsk)
    'sum([_, _, *])'
    """
    if istask(task):
        func = task[0]
        if hasattr(func, 'funcs'):
            head = '('.join(funcname(f) for f in func.funcs)
            tail = ')'*len(func.funcs)
        else:
            head = funcname(task[0])
            tail = ')'
        label_size2 = int((label_size - len(head) - len(tail)) / len(task[1:]))
        if label_size2 > 5:
            args = ', '.join(pprint_task(t, keys, label_size2)
                             for t in task[1:])
        else:
            args = '...'
        result = '{0}({1}{2}'.format(head, args, tail)
    elif isinstance(task, list):
        task2 = task[:3]
        label_size2 = int((label_size - 2 - 2*len(task2)) / len(task2))
        args = ', '.join(pprint_task(t, keys, label_size2) for t in task2)
        if len(task) > 3:
            result = '[{0}, ...]'.format(args)
        else:
            result = '[{0}]'.format(args)
    else:
        try:
            if task in keys:
                result = '_'
            else:
                result = '*'
        except TypeError:
            result = '*'

    return result


def get_colors(palette, funcs):
    """Get a dict mapping funcs to colors from palette.

    Parameters
    ----------
    palette : string
        Name of the palette. Must be a key in bokeh.palettes.brewer
    funcs : iterable
        Iterable of function names
    """
    unique_funcs = list(sorted(unique(funcs)))
    n_funcs = len(unique_funcs)
    palette_lookup = brewer[palette]
    keys = list(palette_lookup.keys())
    low, high = min(keys), max(keys)
    if n_funcs > high:
        colors = cycle(palette_lookup[high])
    elif n_funcs < low:
        colors = palette_lookup[low]
    else:
        colors = palette_lookup[n_funcs]
    color_lookup = dict(zip(unique_funcs, colors))
    return [color_lookup[n] for n in funcs]


def visualize(profilers, file_path=None, show=True, save=True, **kwargs):
    """Visualize the results of profiling in a bokeh plot.

    If multiple profilers are passed in, the plots are stacked vertically.

    Parameters
    ----------
    profilers : profiler or list
        Profiler or list of profilers.
    file_path : string, optional
        Name of the plot output file.
    show : boolean, optional
        If True (default), the plot is opened in a browser.
    save : boolean, optional
        If True (default), the plot is saved to disk.
    **kwargs
        Other keyword arguments, passed to bokeh.figure. These will override
        all defaults set by visualize.

    Returns
    -------
    The completed bokeh plot object.
    """
    if not _state._notebook:
        file_path = file_path or "profile.html"
        bp.output_file(file_path)

    if not isinstance(profilers, list):
        profilers = [profilers]
    figs = [prof._plot(**kwargs) for prof in profilers]
    # Stack the plots
    if len(figs) == 1:
        p = figs[0]
    else:
        top = figs[0]
        for f in figs[1:]:
            f.x_range = top.x_range
            f.title = None
            f.min_border_top = 20
        for f in figs[:1]:
            f.xaxis.axis_label = None
            f.min_border_bottom = 20
        for f in figs:
            f.min_border_left = 75
            f.min_border_right = 75
        p = bp.gridplot([[f] for f in figs])
    if show:
        bp.show(p)
    if file_path and save:
        bp.save(p)
    return p


def plot_tasks(results, dsk, palette='GnBu', label_size=60, **kwargs):
    """Visualize the results of profiling in a bokeh plot.

    Parameters
    ----------
    results : sequence
        Output of Profiler.results
    dsk : dict
        The dask graph being profiled.
    palette : string, optional
        Name of the bokeh palette to use, must be key in bokeh.palettes.brewer.
    label_size: int (optional)
        Maximum size of output labels in plot, defaults to 60
    **kwargs
        Other keyword arguments, passed to bokeh.figure. These will override
        all defaults set by visualize.

    Returns
    -------
    The completed bokeh plot object.
    """

    keys, tasks, starts, ends, ids = zip(*results)

    id_group = groupby(itemgetter(4), results)
    timings = dict((k, [i.end_time - i.start_time for i in v]) for (k, v) in
                   id_group.items())
    id_lk = dict((t[0], n) for (n, t) in enumerate(sorted(timings.items(),
                 key=itemgetter(1), reverse=True)))

    left = min(starts)
    right = max(ends)

    defaults = dict(title="Profile Results",
                    tools="hover,save,reset,resize,xwheel_zoom,xpan",
                    plot_width=800, plot_height=300)
    defaults.update((k, v) for (k, v) in kwargs.items() if k in
                    bp.Figure.properties())

    p = bp.figure(y_range=[str(i) for i in range(len(id_lk))],
                  x_range=[0, right - left], **defaults)

    data = {}
    data['width'] = width = [e - s for (s, e) in zip(starts, ends)]
    data['x'] = [w/2 + s - left for (w, s) in zip(width, starts)]
    data['y'] = [id_lk[i] + 1 for i in ids]
    data['function'] = funcs = [pprint_task(i, dsk, label_size) for i in tasks]
    data['color'] = get_colors(palette, funcs)
    data['key'] = [str(i) for i in keys]

    source = bp.ColumnDataSource(data=data)

    p.rect(source=source, x='x', y='y', height=1, width='width',
           color='color', line_color='gray')
    p.grid.grid_line_color = None
    p.axis.axis_line_color = None
    p.axis.major_tick_line_color = None
    p.yaxis.axis_label = "Worker ID"
    p.xaxis.axis_label = "Time (s)"

    hover = p.select(HoverTool)
    hover.tooltips = """
    <div>
        <span style="font-size: 14px; font-weight: bold;">Key:</span>&nbsp;
        <span style="font-size: 10px; font-family: Monaco, monospace;">@key</span>
    </div>
    <div>
        <span style="font-size: 14px; font-weight: bold;">Task:</span>&nbsp;
        <span style="font-size: 10px; font-family: Monaco, monospace;">@function</span>
    </div>
    """
    hover.point_policy = 'follow_mouse'

    return p


def plot_resources(results, palette='GnBu', **kwargs):
    """Plot resource usage in a bokeh plot.

    Parameters
    ----------
    results : sequence
        Output of ResourceProfiler.results
    palette : string, optional
        Name of the bokeh palette to use, must be key in bokeh.palettes.brewer.
    **kwargs
        Other keyword arguments, passed to bokeh.figure. These will override
        all defaults set by plot_resources.

    Returns
    -------
    The completed bokeh plot object.
    """
    t, mem, cpu = zip(*results)
    left, right = min(t), max(t)
    t = [i - left for i in t]
    defaults = dict(title="Profile Results",
                    tools="save,reset,resize,xwheel_zoom,xpan",
                    plot_width=800, plot_height=300)
    defaults.update((k, v) for (k, v) in kwargs.items() if k in
                    bp.Figure.properties())
    p = bp.figure(y_range=(0, max(cpu)), x_range=(0, right - left), **defaults)
    colors = brewer[palette][6]
    p.line(t, cpu, color=colors[0], line_width=4, legend='% CPU')
    p.yaxis.axis_label = "% CPU"
    p.extra_y_ranges = {'memory': Range1d(start=0, end=max(mem))}
    p.line(t, mem, color=colors[2], y_range_name='memory', line_width=4,
           legend='Memory')
    p.add_layout(LinearAxis(y_range_name='memory', axis_label='Memory (MB)'),
                 'right')
    p.xaxis.axis_label = "Time (s)"
    return p
