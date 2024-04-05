from .sql import Base
from sqlalchemy import DATE, TIMESTAMP, Column, Integer, String, ForeignKey, Float, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "users"

    uid = Column(String(100), primary_key=True)
    First_Name = Column(String(100), nullable=False)
    Last_Name = Column(String(100), nullable=False)
    Email = Column(String(200), nullable=False)
    Phone = Column(String(20))

    Current_Balance = Column(Float)

    Account_Status = Column(Integer)
    
    created_date = Column(DATE, nullable=False, server_default=func.now())
    time_updated = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    transactions_account = relationship('AccountTransactions', backref='user')
    transactions_crypto = relationship('CryptoTransactions', backref='user')
    crypto_holdings = relationship("CryptoHoldings", backref="user")

class Crypto_Prices(Base):
    __tablename__ = "crypto_prices"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    token_id = Column(String(50), nullable=False)
    token_name = Column(String(50), nullable=False)
    token_symbol = Column(String(50), nullable=False)
    token_price = Column(Float, nullable=False)
    price_time = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint('token_id', 'price_time', name='uq_token_id_price_time'),
    )

class AccountTransactions(Base):

    __tablename__ = "transactions_accounts"

    transaction_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(100), ForeignKey("users.uid"))
    transaction_type = Column(String(50), nullable=False)
    quantity = Column(Float)

    transaction_time = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

class CryptoTransactions(Base):

    __tablename__ = "transactions_crypto"

    transaction_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(100), ForeignKey("users.uid"))

    transaction_type = Column(String(50), nullable=False)
    token_id = Column(String(50), nullable=False)
    token_name = Column(String(50), nullable=False)
    token_symbol = Column(String(50), nullable=False)

    token_price = Column(Float, nullable=False)

    quantity = Column(Float)

    transaction_time = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class CryptoHoldings(Base):
    __tablename__ = "crypto_holdings"

    transaction_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(String(100), ForeignKey("users.uid"))

    token_id = Column(String(50), nullable=False)
    token_name = Column(String(50), nullable=False)
    token_symbol = Column(String(50), nullable=False)

    quantity = Column(Float)

    bought_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())