from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BasicModifyCartRequest(BaseModel):

    product_variant_id: int = Field(ge=0)
    qty: int 

    model_config = ConfigDict(extra="forbid")


class AddCartItemRequest(BasicModifyCartRequest):
    pass


class DeleteCartItemResponse(BaseModel):
    message: str
    cart_id: int


class UpdateCartItemRequest(BaseModel):
    qty: int = Field(..., gt=0, description="New quantity for the cart item")

class CartItemResponse(BaseModel):
    id: int
    product_variant_id: int
    qty: int

    # optional fields for UI
    product_name: Optional[str] = None
    variant_label: Optional[str] = None
    price: Optional[int] = None
    stock_qty: Optional[int] = None
    subtotal: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

class CartResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    guest_token: Optional[str] = None
    items: list[CartItemResponse] = []
    total_items: int = 0
    total_price: int = 0

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def validate_identifier_exists(self) -> "CartResponse":
        has_user_id = self.user_id is not None
        has_guest_token = bool(self.guest_token and self.guest_token.strip())

        if not has_user_id and not has_guest_token:
            raise ValueError("Either 'user_id' or a non-empty 'guest_token' must be provided.")

        return self