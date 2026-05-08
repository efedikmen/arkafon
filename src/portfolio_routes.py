"""Multi-basket CRUD endpoints with per-lot acquisition data.

Kept in a dedicated module so api.py stays focused on the analytics surface.
The `register_portfolio_routes(app)` function attaches everything to the
FastAPI app the caller passes in.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db import (
    get_db, User, Portfolio, PortfolioItem,
    BasketCreate, BasketDetail, BasketUpdate, LotIn, LotOut,
)
from src.auth import get_current_user

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _own(db: Session, user: User, basket_id: int) -> Portfolio:
    p = db.query(Portfolio).filter(Portfolio.id == basket_id,
                                    Portfolio.user_id == user.id).first()
    if not p:
        raise HTTPException(404, "basket_not_found")
    return p


@router.get("/baskets")
def list_baskets(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    rows = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
    return [{"id": p.id, "name": p.name, "item_count": len(p.items)} for p in rows]


@router.post("/baskets", response_model=BasketDetail)
def create_basket(payload: BasketCreate,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    name = (payload.name or "").strip() or "Yeni Sepet"
    existing = db.query(Portfolio).filter(
        Portfolio.user_id == user.id, Portfolio.name == name).first()
    if existing:
        raise HTTPException(400, "basket_name_taken")
    p = Portfolio(user_id=user.id, name=name)
    db.add(p); db.commit(); db.refresh(p)
    return p


@router.delete("/baskets/{basket_id}")
def delete_basket(basket_id: int,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    p = _own(db, user, basket_id)
    db.delete(p); db.commit()
    return {"deleted": basket_id}


@router.get("/basket", response_model=BasketDetail)
def get_basket(id: int = 0,
               user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if id:
        p = _own(db, user, id)
    else:
        # Backwards-compatible: first basket; create on miss.
        p = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
        if not p:
            p = Portfolio(user_id=user.id, name="Ana Sepetim")
            db.add(p); db.commit(); db.refresh(p)
    return p


@router.post("/basket/items", response_model=LotOut)
def add_lot(lot: LotIn, basket_id: int = 0,
             user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    if basket_id:
        p = _own(db, user, basket_id)
    else:
        p = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
        if not p:
            raise HTTPException(404, "basket_not_found")
    item = PortfolioItem(
        portfolio_id=p.id,
        fund_code=lot.fund_code,
        acquired_at=lot.acquired_at,
        acquisition_price=lot.acquisition_price,
        quantity=lot.quantity,
    )
    db.add(item); db.commit(); db.refresh(item)
    return item


@router.delete("/basket/items/{item_id}")
def remove_lot(item_id: int,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    item = (db.query(PortfolioItem)
              .join(Portfolio, Portfolio.id == PortfolioItem.portfolio_id)
              .filter(PortfolioItem.id == item_id,
                      Portfolio.user_id == user.id)
              .first())
    if not item:
        raise HTTPException(404, "lot_not_found")
    db.delete(item); db.commit()
    return {"deleted": item_id}


@router.post("/basket")
def replace_basket(basket: BasketUpdate,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Legacy bulk-replace endpoint (kept for backwards compatibility)."""
    if basket.name:
        p = (db.query(Portfolio)
               .filter(Portfolio.user_id == user.id,
                       Portfolio.name == basket.name).first())
    else:
        p = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not p:
        p = Portfolio(user_id=user.id, name=basket.name or "Ana Sepetim")
        db.add(p); db.commit(); db.refresh(p)

    db.query(PortfolioItem).filter(PortfolioItem.portfolio_id == p.id).delete()
    for code in basket.funds:
        db.add(PortfolioItem(portfolio_id=p.id, fund_code=code))
    db.commit()
    return {"status": "success", "name": p.name, "funds": basket.funds}


def register_portfolio_routes(app):
    app.include_router(router)
