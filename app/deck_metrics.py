"""Copy-weighted main-deck statistics, using catalog fields rather than rules text."""
from collections import Counter, defaultdict
import math


def metrics(entries, database, options=None):
    options = options or {}
    available_colors, available_types = set(), set()
    types, tags, curve = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    colors = Counter()
    overall_total = 0
    legends = missing = unknown_cost = known_cost = cost_sum = total = 0
    for entry in entries:
        card = database.get(entry.card_id)
        qty = entry.quantity
        if not card:
            missing += qty
            continue
        if (card.get('card_type') or '').casefold() == 'legend':
            legends += qty
            continue
        overall_total += qty
        raw = card.get('color')
        if isinstance(raw, list):
            color = ' / '.join(sorted(set(str(c).strip().title() for c in raw if c))) or 'Unknown'
        else:
            color = str(raw).strip().title() if raw else 'Unknown'
        card_type = card.get("card_type") or "Unknown"
        available_colors.add(color)
        available_types.add(card_type)
        if options.get("color") and color != options["color"]:
            continue
        if options.get("card_type") and card_type != options["card_type"]:
            continue
        total += qty
        colors[color] += qty
        types[card.get('card_type') or 'Unknown'][color] += qty
        classifications = card.get('classifications') or []
        if isinstance(classifications, str):
            classifications = [classifications]
        for tag in {str(t).strip().title() for t in classifications if str(t).strip()}:
            tags[tag][color] += qty
        cost = card.get('cost')
        try:
            value = float(cost) if cost is not None and not isinstance(cost, bool) else float('nan')
            valid = math.isfinite(value) and value >= 0 and value.is_integer()
        except (ValueError, TypeError):
            valid = False
        bucket = str(int(value)) if valid else 'Unknown'
        curve[bucket][color] += qty
        if valid:
            cost_sum += value * qty
            known_cost += qty
        else:
            unknown_cost += qty
    def rows(groups, order=None):
        names = order or sorted(groups, key=lambda k: (-sum(groups[k].values()), k))
        mode = options.get('sort', 'default')
        if mode == 'count_desc':
            names = sorted(groups, key=lambda k: (-sum(groups[k].values()), k))
        elif mode == 'count_asc':
            names = sorted(groups, key=lambda k: (sum(groups[k].values()), k))
        elif mode == 'name':
            names = sorted(groups, key=lambda k: (k == 'Unknown', int(k) if order and k != 'Unknown' else k))
        return [{'label':name, 'count':sum(groups[name].values()), 'colors':dict(groups[name])} for name in names]
    return {'available_colors':sorted(available_colors), 'available_types':sorted(available_types),
            'filters':{'color':options.get('color',''), 'card_type':options.get('card_type','')},
            'tag_limit':options.get('tag_limit',5), 'overall_total':overall_total, 'total':total, 'legends':legends, 'missing':missing, 'colors':dict(colors),
            'types':rows(types), 'tags':rows(tags)[:options.get('tag_limit',5)],
            'curve':rows(curve, sorted(curve, key=lambda k: (k == 'Unknown', int(k) if k != 'Unknown' else 0))),
            'average_cost':round(cost_sum / known_cost, 2) if known_cost else None,
            'unknown_cost':unknown_cost}
