# {{ meeting.title }} — {{ meeting.date }}

**Type:** {{ meeting.type }} · **Participants:** {{ participants | join(", ") }} · **Minutes by:** {{ uploader }} with bimai
**Source:** transcript `{{ meeting.source_file }}` · every item links to its timestamp

## Summary
{% for s in summary %}
- {{ s.text }} [{{ s.evidence.start }}]
{% endfor %}

## Decisions
| # | Decision | Replaces | At |
|---|---|---|---|
{% for d in decisions %}| {{ d.id }} | {{ d.text }} | {{ d.supersedes | join(", ") or "—" }} | {{ d.evidence.start }} |
{% endfor %}

## Actions
| Action | Who | Position | Due | At |
|---|---|---|---|---|
{% for a in tasks %}| {{ a.text }} | {{ a.person_name }} | {{ a.position or "—" }} | {{ a.due or "—" }} | {{ a.evidence.start }} |
{% endfor %}{% for h in handoffs %}| {{ h.text }} | {{ h.position }} (position) | {{ h.position }} | {{ h.due or "—" }} | {{ h.evidence.start }} |
{% endfor %}

## External actions
{% for e in external %}
- **{{ e.party }}:** {{ e.text }} (due {{ e.due or "—" }}) [{{ e.evidence.start }}]
{% endfor %}

## Risks and issues raised
{% for r in risks %}
- {{ r.text }} [{{ r.evidence.start }}]
{% endfor %}

## Proposed rule changes (waiting for approval)
{% for c in change_requests %}
- {{ c.text }} [{{ c.evidence.start }}]
{% endfor %}

## Parking lot
{% for p in parking_lot %}
- {{ p.text }}{% if p.proposed_owner %} (proposed owner: {{ p.proposed_owner }}){% endif %} [{{ p.evidence.start }}]
{% endfor %}

{% if pending %}
## Still open
{{ pending | length }} item(s) wait for an answer from {{ uploader }} and are not applied yet.
{% endif %}
