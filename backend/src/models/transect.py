from datetime import datetime,timezone
from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,ForeignKey,UniqueConstraint,Integer,DateTime
from src.config.database import Base
class Transect(Base):
 __tablename__='transects'
 __table_args__=(UniqueConstraint('survey_id','reference'),)
 id:Mapped[int]=mapped_column(primary_key=True)
 survey_id:Mapped[int]=mapped_column(ForeignKey('surveys.id'))
 reference:Mapped[str]=mapped_column(String(50))
 name:Mapped[str]=mapped_column(String(100))
 habitat:Mapped[str]=mapped_column(String(80))
 revision:Mapped[int]=mapped_column(Integer,default=1,server_default='1')
 content_hash:Mapped[str|None]=mapped_column(String(64),nullable=True)
 updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))
