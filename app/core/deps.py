from app.db.database import Base, AsyncSessionLocal

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session