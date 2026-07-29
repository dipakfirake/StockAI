from sqlalchemy import Column, Integer, String, Float, Boolean
from backend.core.database import Base

class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value_type = Column(String, default="float") # float, int, string, boolean
    value = Column(String, nullable=False)
    description = Column(String, nullable=True)

    def get_typed_value(self):
        if self.value_type == "float":
            return float(self.value)
        elif self.value_type == "int":
            return int(self.value)
        elif self.value_type == "boolean":
            return self.value.lower() in ("true", "1", "yes")
        return self.value
