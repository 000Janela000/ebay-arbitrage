from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from backend.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables():
    from backend.models import (  # noqa: F401
        Category, EbayCategory, CategoryTreeMeta,
        AuctionItem, PriceEstimate,
        GeorgianListing, Opportunity, CurrencyRate,
        ApiUsage, Setting,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
