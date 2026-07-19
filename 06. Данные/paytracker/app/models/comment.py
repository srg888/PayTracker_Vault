from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class RequestComment(Base):
    __tablename__ = "request_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    request: Mapped["Request"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship()
    attachments: Mapped[list["RequestCommentAttachment"]] = relationship(
        back_populates="comment", cascade="all, delete-orphan"
    )


class RequestCommentAttachment(Base):
    """Файл, прикреплённый к комментарию (например, в рамках цикла "Уточнение" — см.
    01. Процессы/06. Уточнение.md). В отличие от RequestDocument, не привязан к
    DocumentType из справочника и не участвует в проверке комплектности при закрытии
    заявки (см. Бизнес-правила BR-054) — это неформальное вложение к переписке."""

    __tablename__ = "request_comment_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    comment_id: Mapped[int] = mapped_column(
        ForeignKey("request_comments.id", ondelete="CASCADE"), nullable=False
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    comment: Mapped["RequestComment"] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User"] = relationship()
