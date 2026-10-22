"""HTTP boundary for private drafts; installed legacy upload clients stay compatible."""
from fastapi import BackgroundTasks, Depends, Request
from fastapi.responses import Response
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from .domain import Record
from .intake_models import DraftInput, DraftItemInput, DraftEdit, SubmitInput, SourceItemsInput


class Revision(Record):
    expected_revision: int = Field(ge=1)


class Selection(Record):
    item_ids: list[str] = Field(min_length=1, max_length=500)


def public_item(item):
    return {k: v for k, v in item.items() if k not in {'chunks', 'asset', 'thumbnail_ref', 'request_digest'}}


def install_intake_routes(app, prefix, service, *, identity, principal, local_drain=None):
    root = prefix + '/collections/{collection_id}/intake'

    def access(organization_id, collection_id, user):
        return principal(user, organization_id, collection_id, write=True)

    def wake(p, background):
        if local_drain:
            background.add_task(local_drain, p)

    @app.get(root + '/capabilities')
    def capabilities(organization_id: str, collection_id: str, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        return dict(version=1, max_photos=500, max_bytes=25_000_000,
            bulk_source_admission=True, durable_picker_selection=True,
            providers=service.sources.capabilities(p) if service.sources else [],
            worker_configured=bool(service.dispatch_intake or local_drain))

    @app.post(root + '/drafts')
    def create(organization_id: str, collection_id: str, body: DraftInput, user=Depends(identity)):
        return service.create_draft(access(organization_id, collection_id, user), body)

    @app.get(root + '/drafts')
    def drafts(organization_id: str, collection_id: str, after: str = '', limit: int = 50, user=Depends(identity)):
        return service.list(access(organization_id, collection_id, user), 'intake_draft', after=after, limit=limit)

    @app.get(root + '/drafts/{draft_id}')
    def draft(organization_id: str, collection_id: str, draft_id: str, user=Depends(identity)):
        return service.draft(access(organization_id, collection_id, user), draft_id)

    @app.get(root + '/drafts/{draft_id}/items')
    def items(organization_id: str, collection_id: str, draft_id: str, after: int = 0, limit: int = 50, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        draft = service.draft(p, draft_id)
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid page bounds')
        entries = draft['entries'][after:after + limit]
        if draft['state'] == 'discarded':
            return dict(items=[], next_cursor=None)
        selected = service.read_many(p, 'intake_item', [e['id'] for e in entries])
        rows = [dict(public_item(selected[e['id']]), **{k: v for k, v in e.items() if k != 'id'}) for e in entries if e['id'] in selected]
        return dict(items=rows, next_cursor=after + limit if after + limit < len(draft['entries']) else None)

    @app.post(root + '/drafts/{draft_id}/items')
    def add(organization_id: str, collection_id: str, draft_id: str, body: DraftItemInput, background_tasks: BackgroundTasks, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        result = service.add_item(p, draft_id, body)
        wake(p, background_tasks)
        return public_item(result)

    def source_batch(organization_id, collection_id, draft_id, body, background, user, *, reconcile=False):
        p = access(organization_id, collection_id, user)
        method = service.reconcile_sources if reconcile else service.add_sources
        result = method(p, draft_id, body.items)
        wake(p, background)
        return dict(result, items=[public_item(item) for item in result['items']])

    @app.post(root + '/drafts/{draft_id}/items/bulk')
    def add_sources(organization_id: str, collection_id: str, draft_id: str, body: SourceItemsInput,
                    background_tasks: BackgroundTasks, user=Depends(identity)):
        return source_batch(organization_id, collection_id, draft_id, body, background_tasks, user)

    @app.post(root + '/drafts/{draft_id}/items/reconcile')
    def reconcile_sources(organization_id: str, collection_id: str, draft_id: str, body: SourceItemsInput,
                          background_tasks: BackgroundTasks, user=Depends(identity)):
        return source_batch(organization_id, collection_id, draft_id, body, background_tasks, user, reconcile=True)

    @app.post(root + '/drafts/{draft_id}/edit')
    def edit(organization_id: str, collection_id: str, draft_id: str, body: DraftEdit, user=Depends(identity)):
        return service.edit(access(organization_id, collection_id, user), draft_id, body)

    @app.post(root + '/drafts/{draft_id}/discard')
    def discard(organization_id: str, collection_id: str, draft_id: str, body: Revision, user=Depends(identity)):
        return service.discard(access(organization_id, collection_id, user), draft_id, body.expected_revision)

    @app.get(root + '/items/{item_id}')
    def item(organization_id: str, collection_id: str, item_id: str, user=Depends(identity)):
        return public_item(service.item(access(organization_id, collection_id, user), item_id))

    @app.put(root + '/items/{item_id}/content')
    async def content(organization_id: str, collection_id: str, item_id: str, request: Request, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        data = bytearray()
        async for part in request.stream():
            data.extend(part)
            if len(data) > 4 * 1024 * 1024:
                raise ValueError('Chunk exceeds 4 MiB')
        return public_item(await run_in_threadpool(service.content, p, item_id,
            int(request.headers.get('Upload-Offset', '0')), bytes(data)))

    @app.post(root + '/items/{item_id}/save')
    def save(organization_id: str, collection_id: str, item_id: str, background_tasks: BackgroundTasks, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        if service.synthetic:
            result = service.stage(p, item_id)
        else:
            result = service.item(p, item_id)
            if result['offset'] != result['size_bytes']:
                raise ValueError('This photo still needs its remaining bytes')
            if result['state'] != 'ready':
                result.update(state='checking', error=None)
                result = service.save(p, 'intake_item', result)
                service.enqueue(p, item_id, 'stage')
        wake(p, background_tasks)
        return public_item(result)

    @app.post(root + '/items/{item_id}/retry')
    def retry_item(organization_id: str, collection_id: str, item_id: str, background_tasks: BackgroundTasks, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        item = service.item(p, item_id)
        if item['state'] != 'ready':
            item.update(state='waiting', error=None)
            item = service.save(p, 'intake_item', item)
            service.enqueue(p, item_id, 'stage')
        wake(p, background_tasks)
        return public_item(item)

    @app.get(root + '/items/{item_id}/preview')
    def preview(organization_id: str, collection_id: str, item_id: str, full: bool = False, user=Depends(identity)):
        item = service.item(access(organization_id, collection_id, user), item_id)
        if item['state'] != 'ready':
            return Response(status_code=204, headers={'Cache-Control': 'no-store'})
        ref = item['asset']['view_derivative']['blob_ref'] if full else item['thumbnail_ref']
        return Response(service.blobs.get(ref), media_type='image/png' if full else 'image/jpeg',
                        headers={'Cache-Control': 'private, no-store'})

    @app.post(root + '/drafts/{draft_id}/submit', status_code=202)
    def submit(organization_id: str, collection_id: str, draft_id: str, body: SubmitInput, background_tasks: BackgroundTasks, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        result = service.submit(p, draft_id, body)
        wake(p, background_tasks)
        return result

    @app.get(root + '/submissions')
    def submissions(organization_id: str, collection_id: str, after: str = '', limit: int = 50, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        page = service.list(p, 'intake_submission', after=after, limit=limit)
        return dict(page, items=[service.submission(p, row['id']) for row in page['items']])

    @app.get(root + '/submissions/{submission_id}')
    def submission(organization_id: str, collection_id: str, submission_id: str, user=Depends(identity)):
        return service.submission(access(organization_id, collection_id, user), submission_id)

    @app.get(root + '/submissions/{submission_id}/items')
    def submission_items(organization_id: str, collection_id: str, submission_id: str, after: int = 0, limit: int = 50, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        doc = service.read(p, 'intake_submission', submission_id)
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError('Invalid page bounds')
        return dict(items=service.results(p, doc, doc['entries'][after:after + limit]),
                    next_cursor=after + limit if after + limit < doc['total'] else None)

    @app.post(root + '/submissions/{submission_id}/retry')
    def retry(organization_id: str, collection_id: str, submission_id: str, body: Selection, background_tasks: BackgroundTasks, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        result = service.retry(p, submission_id, body.item_ids)
        wake(p, background_tasks)
        return result

    @app.post(root + '/submissions/{submission_id}/cancel')
    def cancel(organization_id: str, collection_id: str, submission_id: str, background_tasks: BackgroundTasks, user=Depends(identity)):
        p = access(organization_id, collection_id, user)
        result = service.cancel(p, submission_id)
        wake(p, background_tasks)
        return result
