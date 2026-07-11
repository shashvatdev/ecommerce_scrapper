"""
FastAPI Backend — E-Commerce Scraper
Endpoints: scrape, products, export (CSV/JSON/Excel), delete
"""

import io
import csv
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import init_db, get_db, ProductDB, PriceHistoryDB
from models import ScrapeRequest, ScrapeResponse, Product, ProductListItem, PricePoint
from scrapers import scrape_amazon, scrape_flipkart

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="E-Commerce Scraper API",
    description="Scrape Amazon & Flipkart product data",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    logger.info("Database initialized.")


# ── Helpers ───────────────────────────────────────────────────────────────────
def save_product(db: Session, data: dict) -> ProductDB:
    """
    Upsert product: update existing if same platform+product_id,
    else insert new. Always appends a price history entry.
    """
    existing = (
        db.query(ProductDB)
        .filter_by(platform=data["platform"], product_id=data["product_id"])
        .first()
    )

    if existing:
        for key, val in data.items():
            setattr(existing, key, val)
        existing.last_updated = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        product = existing
    else:
        product = ProductDB(**data)
        db.add(product)
        db.commit()
        db.refresh(product)

    # Record price history
    if data.get("price"):
        ph = PriceHistoryDB(product_id=product.id, price=data["price"])
        db.add(ph)
        db.commit()

    return product


def db_product_to_schema(product: ProductDB, db: Session) -> Product:
    history = (
        db.query(PriceHistoryDB)
        .filter_by(product_id=product.id)
        .order_by(PriceHistoryDB.recorded_at)
        .all()
    )
    price_history = [
        PricePoint(price=ph.price, recorded_at=ph.recorded_at)
        for ph in history
    ]
    return Product(
        id=product.id,
        platform=product.platform,
        product_id=product.product_id,
        title=product.title,
        brand=product.brand,
        price=product.price,
        mrp=product.mrp,
        discount=product.discount,
        rating=product.rating,
        review_count=product.review_count,
        seller=product.seller,
        availability=product.availability,
        image_url=product.image_url,
        product_url=product.product_url,
        scraped_at=product.scraped_at,
        last_updated=product.last_updated,
        price_history=price_history,
    )


# ── Scrape Endpoints ──────────────────────────────────────────────────────────
@app.post("/scrape/amazon", response_model=ScrapeResponse)
async def scrape_amazon_endpoint(req: ScrapeRequest, db: Session = Depends(get_db)):
    try:
        data = await scrape_amazon(req.input, req.type)
        product = save_product(db, data)
        return ScrapeResponse(
            success=True,
            message="Amazon product scraped successfully.",
            product=db_product_to_schema(product, db),
        )
    except Exception as e:
        logger.error(f"Amazon scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/flipkart", response_model=ScrapeResponse)
async def scrape_flipkart_endpoint(req: ScrapeRequest, db: Session = Depends(get_db)):
    try:
        data = await scrape_flipkart(req.input, req.type)
        product = save_product(db, data)
        return ScrapeResponse(
            success=True,
            message="Flipkart product scraped successfully.",
            product=db_product_to_schema(product, db),
        )
    except Exception as e:
        logger.error(f"Flipkart scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scrape/both", response_model=dict)
async def scrape_both_endpoint(req: ScrapeRequest, db: Session = Depends(get_db)):
    """Scrape the same query on both platforms concurrently."""
    amazon_result, flipkart_result = await asyncio.gather(
        scrape_amazon(req.input, req.type),
        scrape_flipkart(req.input, req.type),
        return_exceptions=True,
    )

    results = {}
    if isinstance(amazon_result, Exception):
        results["amazon"] = {"success": False, "error": str(amazon_result)}
    else:
        p = save_product(db, amazon_result)
        results["amazon"] = {"success": True, "product": db_product_to_schema(p, db).model_dump()}

    if isinstance(flipkart_result, Exception):
        results["flipkart"] = {"success": False, "error": str(flipkart_result)}
    else:
        p = save_product(db, flipkart_result)
        results["flipkart"] = {"success": True, "product": db_product_to_schema(p, db).model_dump()}

    return results


# ── Product Endpoints ─────────────────────────────────────────────────────────
@app.get("/products", response_model=list[ProductListItem])
def list_products(
    platform: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ProductDB)
    if platform:
        query = query.filter(ProductDB.platform == platform)
    products = query.order_by(ProductDB.scraped_at.desc()).all()
    return products


@app.get("/products/{product_id}", response_model=Product)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return db_product_to_schema(product, db)


@app.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(ProductDB).filter(ProductDB.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    db.query(PriceHistoryDB).filter(PriceHistoryDB.product_id == product_id).delete()
    db.delete(product)
    db.commit()
    return {"success": True, "message": "Product deleted."}


@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(ProductDB).count()
    amazon_count = db.query(ProductDB).filter_by(platform="amazon").count()
    flipkart_count = db.query(ProductDB).filter_by(platform="flipkart").count()

    all_prices = [p.price for p in db.query(ProductDB).all() if p.price]
    avg_price = round(sum(all_prices) / len(all_prices), 2) if all_prices else 0

    return {
        "total_products": total,
        "amazon_count": amazon_count,
        "flipkart_count": flipkart_count,
        "average_price": avg_price,
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ── Export Endpoints ──────────────────────────────────────────────────────────
@app.get("/export/csv")
def export_csv(db: Session = Depends(get_db)):
    products = db.query(ProductDB).order_by(ProductDB.scraped_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Platform", "Product ID", "Title", "Brand",
        "Price", "MRP", "Discount %", "Rating", "Reviews",
        "Seller", "Availability", "Image URL", "Product URL", "Scraped At",
    ])
    for p in products:
        writer.writerow([
            p.id, p.platform, p.product_id, p.title, p.brand,
            p.price, p.mrp, p.discount, p.rating, p.review_count,
            p.seller, p.availability, p.image_url, p.product_url,
            p.scraped_at.isoformat() if p.scraped_at else "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products.csv"},
    )


@app.get("/export/json")
def export_json(db: Session = Depends(get_db)):
    products = db.query(ProductDB).order_by(ProductDB.scraped_at.desc()).all()
    data = []
    for p in products:
        data.append({
            "id": p.id, "platform": p.platform, "product_id": p.product_id,
            "title": p.title, "brand": p.brand, "price": p.price,
            "mrp": p.mrp, "discount": p.discount, "rating": p.rating,
            "review_count": p.review_count, "seller": p.seller,
            "availability": p.availability, "image_url": p.image_url,
            "product_url": p.product_url,
            "scraped_at": p.scraped_at.isoformat() if p.scraped_at else None,
        })
    output = json.dumps(data, indent=2, ensure_ascii=False)
    return StreamingResponse(
        iter([output]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=products.json"},
    )


@app.get("/export/excel")
def export_excel(db: Session = Depends(get_db)):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl not installed")

    products = db.query(ProductDB).order_by(ProductDB.scraped_at.desc()).all()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Products"

    headers = [
        "ID", "Platform", "Product ID", "Title", "Brand",
        "Price (₹)", "MRP (₹)", "Discount %", "Rating", "Reviews",
        "Seller", "Availability", "Product URL", "Scraped At",
    ]

    # Style header row
    header_fill = PatternFill(start_color="1a1a2e", end_color="1a1a2e", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")

    # Data rows
    for row, p in enumerate(products, 2):
        ws.append([
            p.id, p.platform, p.product_id, p.title, p.brand,
            p.price, p.mrp, p.discount, p.rating, p.review_count,
            p.seller, p.availability, p.product_url,
            p.scraped_at.isoformat() if p.scraped_at else "",
        ])

    # Auto-width columns
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=products.xlsx"},
    )
