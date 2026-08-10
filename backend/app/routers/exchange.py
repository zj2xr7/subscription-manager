from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AppSettings
from ..services.exchange_rate import exchange_rate_service

router = APIRouter(prefix="/api/exchange", tags=["exchange"])


@router.get("/rates")
async def get_rates(base: str = Query("USD", pattern="^(USD|GBP|CAD|CNY)$"), db: Session = Depends(get_db)):
    setting = db.get(AppSettings, "exchange_rate_api_key")
    values = await exchange_rate_service.rates(base, setting.value if setting else "")
    return {"base": base, "rates": {code: values[code] for code in ("USD", "GBP", "CAD", "CNY") if code in values}}


@router.get("/quotes")
async def get_cny_quotes(refresh: bool = False, db: Session = Depends(get_db)):
    setting = db.get(AppSettings, "exchange_rate_api_key")
    return await exchange_rate_service.cny_quotes(setting.value if setting else "", refresh=refresh)
