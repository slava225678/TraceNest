from pathlib import Path
from typing import Annotated
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.events import DatabaseSession
from app.groups import list_group_events, list_groups
from app.models import ErrorGroup, Event

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
PAGE_SIZE = 20
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "connect-src 'self'; img-src 'none'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}


def render(request, template, context, status_code=200):
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=context,
        status_code=status_code,
        headers=HEADERS,
    )


def render_error(request, status_code, message):
    return render(
        request,
        "error.html",
        {"status_code": status_code, "message": message},
        status_code,
    )


def page_links(request: Request, offset: int, has_next: bool) -> dict:
    def link(value):
        params = dict(request.query_params)
        params["offset"] = value
        return request.url.path + "?" + urlencode(params)

    return {
        "previous_url": link(max(0, offset - PAGE_SIZE)) if offset else None,
        "next_url": link(offset + PAGE_SIZE) if has_next else None,
        "page": offset // PAGE_SIZE + 1,
    }


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: DatabaseSession,
    status: Annotated[str, Query(pattern="^(unresolved|resolved)?$")] = "",
    application: Annotated[str, Query(max_length=200)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
):
    groups = list_groups(
        session,
        limit=PAGE_SIZE + 1,
        offset=offset,
        status=status or None,
        application=application or None,
    )
    totals = session.execute(
        select(
            func.count(ErrorGroup.id).label("groups"),
            func.coalesce(func.sum(ErrorGroup.occurrences), 0).label("events"),
            func.count()
            .filter(ErrorGroup.status == "unresolved")
            .label("unresolved"),
            func.count()
            .filter(ErrorGroup.status == "resolved")
            .label("resolved"),
        )
    ).one()
    applications = list(
        session.scalars(
            select(ErrorGroup.application)
            .where(ErrorGroup.application.is_not(None))
            .distinct()
            .order_by(ErrorGroup.application)
        )
    )
    return render(
        request,
        "groups.html",
        {
            "groups": groups[:PAGE_SIZE],
            "totals": totals,
            "applications": applications,
            "status": status,
            "application": application,
            **page_links(request, offset, len(groups) > PAGE_SIZE),
        },
    )


@router.get("/groups/{group_id}", response_class=HTMLResponse)
def group_detail(
    group_id: UUID,
    request: Request,
    session: DatabaseSession,
    event_id: UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    group = session.get(ErrorGroup, group_id)
    if group is None:
        return render_error(request, 404, "This error group was not found.")
    history = list_group_events(
        group_id, session, limit=PAGE_SIZE + 1, offset=offset
    )
    statement = select(Event).where(Event.group_id == group_id)
    if event_id is not None:
        statement = statement.where(Event.id == event_id)
    selected = session.scalar(
        statement.order_by(Event.created_at.desc(), Event.id.desc()).limit(1)
    )
    if event_id is not None and selected is None:
        return render_error(request, 404, "This event is not in this group.")
    return render(
        request,
        "detail.html",
        {
            "group": group,
            "history": history[:PAGE_SIZE],
            "selected": selected,
            **page_links(request, offset, len(history) > PAGE_SIZE),
        },
    )
