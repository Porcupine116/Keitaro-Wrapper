from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.schemas.campaign import CampaignCreate, OfferAdd
from app.services.campaign_service import CampaignService
from app.services.keitaro_client import KeitaroClient, KeitaroError

router = APIRouter(prefix="/api")


def get_service() -> KeitaroClient:
    try:
        return KeitaroClient()
    except KeitaroError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/references")
async def references(api: KeitaroClient = Depends(get_service)):
    try:
        return await CampaignService(api).references()
    except KeitaroError as exc:
        raise _keitaro_http_error(exc) from exc
    finally:
        await api.close()


@router.get("/keitaro/info")
async def keitaro_info():
    from app.core.config import settings

    tracker_url = settings.keitaro_base_url.rstrip("/") if settings.keitaro_base_url else None
    if tracker_url:
        api_prefix = "/" + settings.keitaro_api_prefix.strip("/")
        if tracker_url.lower().endswith(api_prefix.lower()):
            tracker_url = tracker_url[:-len(api_prefix)].rstrip("/")
    return {"tracker_url": tracker_url}


@router.get("/keitaro/metadata")
async def keitaro_metadata():
    return {
        "source": "Adrobot test stand specification",
        "schemas": ["redirect", "landings"],
        "types": ["regular", "default"],
        "actions": ["http"],
        "filters": ["country"],
        "unsupported_endpoints": [
            "/stream_filters",
            "/streams_actions",
            "/stream_types",
            "/stream_schemas",
        ],
    }


@router.get("/campaigns")
async def campaigns(api: KeitaroClient = Depends(get_service)):
    try:
        result = await api.get("campaigns", params={"limit": 100, "offset": 0})
        return result if isinstance(result, list) else []
    except KeitaroError as exc:
        raise _keitaro_http_error(exc) from exc
    finally:
        await api.close()


@router.post("/campaigns")
async def create_campaign(
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    api: KeitaroClient = Depends(get_service),
):
    data = payload.model_dump()
    try:
        result = await CampaignService(api).create_campaign(data)
        db.add(AuditLog(
            operation="create_campaign",
            entity_type="campaign",
            entity_id=str(result["campaign_id"]),
            status="success",
            request_data=data,
            response_data={"alias": result.get("alias"), "streams": result.get("streams", [])},
        ))
        db.commit()
        return result
    except (KeitaroError, ValueError) as exc:
        error_details = getattr(exc, "details", None)
        partial_campaign_id = error_details.get("campaign_id") if isinstance(error_details, dict) else None
        db.add(AuditLog(
            operation="create_campaign",
            entity_type="campaign",
            entity_id=str(partial_campaign_id) if partial_campaign_id else None,
            status="error",
            request_data=data,
            error_message=str(exc),
            response_data=getattr(exc, "details", None),
        ))
        db.commit()
        if isinstance(exc, KeitaroError):
            raise _keitaro_http_error(exc) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await api.close()


@router.get("/campaigns/{campaign_id}/streams")
async def campaign_streams(campaign_id: int, api: KeitaroClient = Depends(get_service)):
    try:
        return await CampaignService(api).get_campaign_streams(campaign_id)
    except KeitaroError as exc:
        raise _keitaro_http_error(exc) from exc
    finally:
        await api.close()


@router.post("/campaigns/{campaign_id}/streams/{stream_id}/offers")
async def add_offer(
    campaign_id: int,
    stream_id: int,
    payload: OfferAdd,
    db: Session = Depends(get_db),
    api: KeitaroClient = Depends(get_service),
):
    try:
        result = await CampaignService(api).add_offer(campaign_id, stream_id, payload.offer_id)
        db.add(AuditLog(
            operation="add_offer", entity_type="stream", entity_id=str(stream_id),
            status="success", request_data={"campaign_id": campaign_id, **payload.model_dump()},
            response_data={"offers": result.get("offers", [])},
        ))
        db.commit()
        return result
    except (KeitaroError, ValueError) as exc:
        db.rollback()
        if isinstance(exc, KeitaroError):
            raise _keitaro_http_error(exc) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await api.close()


@router.delete("/campaigns/{campaign_id}/streams/{stream_id}/offers/{offer_id}")
async def remove_offer(
    campaign_id: int,
    stream_id: int,
    offer_id: int,
    db: Session = Depends(get_db),
    api: KeitaroClient = Depends(get_service),
):
    try:
        result = await CampaignService(api).remove_offer(campaign_id, stream_id, offer_id)
        db.add(AuditLog(
            operation="remove_offer", entity_type="stream", entity_id=str(stream_id),
            status="success",
            request_data={"campaign_id": campaign_id, "offer_id": offer_id},
            response_data={"offers": result.get("offers", [])},
        ))
        db.commit()
        return result
    except (KeitaroError, ValueError) as exc:
        db.rollback()
        if isinstance(exc, KeitaroError):
            raise _keitaro_http_error(exc) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await api.close()


def _keitaro_http_error(exc: KeitaroError) -> HTTPException:
    status = 502
    if exc.status_code in (400, 401, 402, 404, 406):
        status = 502  # ошибка внешнего API, не ошибка нашего HTTP-запроса
    return HTTPException(status_code=status, detail={"message": str(exc), "keitaro": exc.details})
