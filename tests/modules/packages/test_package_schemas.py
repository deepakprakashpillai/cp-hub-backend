import pytest
from pydantic import ValidationError

from app.modules.packages.schemas import PackageCreate


def test_package_create_defaults_to_inr_and_active() -> None:
    package = PackageCreate(
        name="1 Month IELTS",
        duration_days=30,
        price_amount=500000,
    )

    assert package.currency == "INR"
    assert package.is_active is True


@pytest.mark.parametrize(
    ("duration_days", "price_amount"),
    [
        (0, 500000),
        (30, -1),
    ],
)
def test_package_create_rejects_invalid_duration_or_price(
    duration_days: int,
    price_amount: int,
) -> None:
    with pytest.raises(ValidationError):
        PackageCreate(
            name="Invalid package",
            duration_days=duration_days,
            price_amount=price_amount,
        )
