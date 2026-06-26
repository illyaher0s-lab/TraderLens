from unittest import TestCase

from strategy_core.position_sizer import PositionSizer


class TestPositionSizer(TestCase):
    def test_position_sizer_calculates_quantity_with_default_ratio(self):
        """
        Default position_ratio is 0.2 (20% of available capital per position).
        """
        sizer = PositionSizer()
        # available_capital=10000, ratio=0.2 => budget=2000
        # price=10 => shares=200 => lots=2 => quantity=200
        quantity = sizer.calculate_quantity(price=10.0, available_capital=10000.0)
        self.assertEqual(quantity, 200)

    def test_position_sizer_rounds_down_to_lot_size(self):
        """
        Quantity must be rounded down to multiples of lot_size (100 shares).
        """
        sizer = PositionSizer(position_ratio=0.2)
        # available_capital=10000, ratio=0.2 => budget=2000
        # price=15 => shares=133 => lots=1 => quantity=100
        quantity = sizer.calculate_quantity(price=15.0, available_capital=10000.0)
        self.assertEqual(quantity, 100)

    def test_position_sizer_returns_zero_when_capital_insufficient(self):
        """
        When budget is insufficient to buy one lot, return 0.
        """
        sizer = PositionSizer(position_ratio=0.2)
        # available_capital=1000, ratio=0.2 => budget=200
        # price=50 => shares=4 => lots=0 => quantity=0
        quantity = sizer.calculate_quantity(price=50.0, available_capital=1000.0)
        self.assertEqual(quantity, 0)

    def test_position_sizer_respects_custom_position_ratio(self):
        """
        position_ratio can be customized.
        """
        sizer = PositionSizer(position_ratio=0.5)
        # available_capital=10000, ratio=0.5 => budget=5000
        # price=10 => shares=500 => lots=5 => quantity=500
        quantity = sizer.calculate_quantity(price=10.0, available_capital=10000.0)
        self.assertEqual(quantity, 500)

    def test_position_sizer_rejects_invalid_price(self):
        """
        Price must be positive.
        """
        sizer = PositionSizer()
        with self.assertRaises(ValueError) as ctx:
            sizer.calculate_quantity(price=0.0, available_capital=10000.0)
        self.assertIn("price must be positive", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            sizer.calculate_quantity(price=-10.0, available_capital=10000.0)
        self.assertIn("price must be positive", str(ctx.exception))

    def test_position_sizer_rejects_negative_capital(self):
        """
        available_capital cannot be negative.
        """
        sizer = PositionSizer()
        with self.assertRaises(ValueError) as ctx:
            sizer.calculate_quantity(price=10.0, available_capital=-1000.0)
        self.assertIn("available_capital cannot be negative", str(ctx.exception))

    def test_position_sizer_rejects_invalid_position_ratio(self):
        """
        position_ratio must be in (0, 1].
        """
        with self.assertRaises(ValueError) as ctx:
            PositionSizer(position_ratio=0.0)
        self.assertIn("position_ratio must be in (0, 1]", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            PositionSizer(position_ratio=1.5)
        self.assertIn("position_ratio must be in (0, 1]", str(ctx.exception))

    def test_position_sizer_allows_full_capital_position(self):
        """
        position_ratio=1.0 is valid (use all available capital).
        """
        sizer = PositionSizer(position_ratio=1.0)
        # available_capital=10000, ratio=1.0 => budget=10000
        # price=20 => shares=500 => lots=5 => quantity=500
        quantity = sizer.calculate_quantity(price=20.0, available_capital=10000.0)
        self.assertEqual(quantity, 500)

    def test_position_sizer_handles_zero_available_capital(self):
        """
        When available_capital is 0, return 0.
        """
        sizer = PositionSizer()
        quantity = sizer.calculate_quantity(price=10.0, available_capital=0.0)
        self.assertEqual(quantity, 0)
