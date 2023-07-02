// -------------------------------------------------------------------------------------------------
//  Copyright (C) 2015-2023 Nautech Systems Pty Ltd. All rights reserved.
//  https://nautechsystems.io
//
//  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
//  You may not use this file except in compliance with the License.
//  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
//
//  Unless required by applicable law or agreed to in writing, software
//  distributed under the License is distributed on an "AS IS" BASIS,
//  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//  See the License for the specific language governing permissions and
//  limitations under the License.
// -------------------------------------------------------------------------------------------------

use std::{
    fmt::{Display, Formatter},
    hash::{Hash, Hasher},
    str::FromStr,
};

use nautilus_core::serialization::Serializable;
use pyo3::{
    exceptions::{PyKeyError, PyValueError},
    prelude::*,
    pyclass::CompareOp,
    types::PyDict,
};
use serde::{Deserialize, Serialize};

use super::{quote::QuoteTick, trade::TradeTick};
use crate::{
    enums::OrderSide,
    orderbook::{book::BookIntegrityError, ladder::BookPrice},
    types::{price::Price, quantity::Quantity},
};

/// Represents an order in a book.
#[repr(C)]
#[derive(Copy, Clone, Eq, Debug, Serialize, Deserialize)]
#[pyclass]
pub struct BookOrder {
    /// The order side.
    pub side: OrderSide,
    /// The order price.
    pub price: Price,
    /// The order size.
    pub size: Quantity,
    /// The order ID.
    pub order_id: u64,
}

impl BookOrder {
    #[must_use]
    pub fn new(side: OrderSide, price: Price, size: Quantity, order_id: u64) -> Self {
        Self {
            side,
            price,
            size,
            order_id,
        }
    }

    #[must_use]
    pub fn to_book_price(&self) -> BookPrice {
        BookPrice::new(self.price, self.side)
    }

    #[must_use]
    pub fn exposure_f64(&self) -> f64 {
        self.price.as_f64() * self.size.as_f64()
    }

    #[must_use]
    pub fn signed_size_f64(&self) -> f64 {
        match self.side {
            OrderSide::Buy => self.size.as_f64(),
            OrderSide::Sell => -(self.size.as_f64()),
            _ => panic!("{}", BookIntegrityError::NoOrderSide),
        }
    }

    #[must_use]
    pub fn from_quote_tick(tick: &QuoteTick, side: OrderSide) -> Self {
        match side {
            OrderSide::Buy => {
                Self::new(OrderSide::Buy, tick.bid, tick.bid_size, tick.bid.raw as u64)
            }
            OrderSide::Sell => Self::new(
                OrderSide::Sell,
                tick.ask,
                tick.ask_size,
                tick.ask.raw as u64,
            ),
            _ => panic!("{}", BookIntegrityError::NoOrderSide),
        }
    }

    #[must_use]
    pub fn from_trade_tick(tick: &TradeTick, side: OrderSide) -> Self {
        match side {
            OrderSide::Buy => {
                Self::new(OrderSide::Buy, tick.price, tick.size, tick.price.raw as u64)
            }
            OrderSide::Sell => Self::new(
                OrderSide::Sell,
                tick.price,
                tick.size,
                tick.price.raw as u64,
            ),
            _ => panic!("{}", BookIntegrityError::NoOrderSide),
        }
    }
}

impl Serializable for BookOrder {}

impl PartialEq for BookOrder {
    fn eq(&self, other: &Self) -> bool {
        self.order_id == other.order_id
    }
}

impl Hash for BookOrder {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.order_id.hash(state);
    }
}

impl Display for BookOrder {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{},{},{},{}",
            self.price, self.size, self.side, self.order_id,
        )
    }
}

#[pymethods]
impl BookOrder {
    #[new]
    fn py_new(side: OrderSide, price: Price, size: Quantity, order_id: u64) -> Self {
        Self::new(side, price, size, order_id)
    }

    fn __richcmp__(&self, other: &Self, op: CompareOp, py: Python<'_>) -> Py<PyAny> {
        match op {
            CompareOp::Eq => self.eq(other).into_py(py),
            CompareOp::Ne => self.ne(other).into_py(py),
            _ => py.NotImplemented(),
        }
    }

    fn __str__(&self) -> String {
        self.to_string()
    }

    fn __repr__(&self) -> String {
        format!("{self:?}")
    }

    #[getter]
    fn side(&self) -> OrderSide {
        self.side
    }

    #[getter]
    fn price(&self) -> Price {
        self.price
    }

    #[getter]
    fn size(&self) -> Quantity {
        self.size
    }

    #[getter]
    fn order_id(&self) -> u64 {
        self.order_id
    }

    fn exposure(&self) -> f64 {
        self.exposure_f64()
    }

    fn signed_size(&self) -> f64 {
        self.signed_size_f64()
    }

    /// Return a dictionary representation of the object.
    fn as_dict(&self) -> Py<PyDict> {
        Python::with_gil(|py| {
            let dict = PyDict::new(py);

            dict.set_item("type", stringify!(BookOrder)).unwrap();
            dict.set_item("side", self.side.to_string()).unwrap();
            dict.set_item("price", self.price.to_string()).unwrap();
            dict.set_item("size", self.size.to_string()).unwrap();
            dict.set_item("order_id", self.order_id).unwrap();

            dict.into_py(py)
        })
    }

    #[staticmethod]
    pub fn from_dict(values: &PyDict) -> PyResult<Self> {
        // Extract values from dictionary
        let side: String = values
            .get_item("side")
            .ok_or(PyKeyError::new_err("'side' not found in `values`"))?
            .extract()?;
        let price: String = values
            .get_item("price")
            .ok_or(PyKeyError::new_err("'price' not found in `values`"))?
            .extract()?;
        let size: String = values
            .get_item("size")
            .ok_or(PyKeyError::new_err("'size' not found in `values`"))?
            .extract()?;
        let order_id: u64 = values
            .get_item("order_id")
            .ok_or(PyKeyError::new_err("'order_id' not found in `values`"))?
            .extract()?;

        let side = OrderSide::from_str(&side).map_err(|e| PyValueError::new_err(e.to_string()))?;
        let price = Price::from_str(&price).map_err(PyValueError::new_err)?;
        let size = Quantity::from_str(&size).map_err(PyValueError::new_err)?;

        Ok(Self::new(side, price, size, order_id))
    }

    #[staticmethod]
    fn from_json(data: Vec<u8>) -> PyResult<Self> {
        match Self::from_json_bytes(data) {
            Ok(quote) => Ok(quote),
            Err(err) => Err(PyValueError::new_err(format!(
                "Failed to deserialize JSON: {}",
                err
            ))),
        }
    }

    #[staticmethod]
    fn from_msgpack(data: Vec<u8>) -> PyResult<Self> {
        match Self::from_msgpack_bytes(data) {
            Ok(quote) => Ok(quote),
            Err(err) => Err(PyValueError::new_err(format!(
                "Failed to deserialize MsgPack: {}",
                err
            ))),
        }
    }

    /// Return JSON encoded bytes representation of the object.
    fn as_json(&self) -> Py<PyAny> {
        // Unwrapping is safe when serializing a valid object
        Python::with_gil(|py| self.as_json_bytes().unwrap().into_py(py))
    }

    /// Return MsgPack encoded bytes representation of the object.
    fn as_msgpack(&self) -> Py<PyAny> {
        // Unwrapping is safe when serializing a valid object
        Python::with_gil(|py| self.as_msgpack_bytes().unwrap().into_py(py))
    }
}

////////////////////////////////////////////////////////////////////////////////
// Tests
////////////////////////////////////////////////////////////////////////////////

#[cfg(test)]
mod tests {
    use std::str::FromStr;

    use rstest::rstest;

    use super::*;
    use crate::{
        enums::AggressorSide,
        identifiers::{instrument_id::InstrumentId, trade_id::TradeId},
    };

    fn create_stub_book_order() -> BookOrder {
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;

        BookOrder::new(side, price, size, order_id)
    }

    #[test]
    fn test_new() {
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;

        let order = BookOrder::new(side, price.clone(), size.clone(), order_id);

        assert_eq!(order.price, price);
        assert_eq!(order.size, size);
        assert_eq!(order.side, side);
        assert_eq!(order.order_id, order_id);
    }

    #[test]
    fn test_to_book_price() {
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;

        let order = BookOrder::new(side, price.clone(), size.clone(), order_id);
        let book_price = order.to_book_price();

        assert_eq!(book_price.value, price);
        assert_eq!(book_price.side, side);
    }

    #[test]
    fn test_exposure() {
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;

        let order = BookOrder::new(side, price.clone(), size.clone(), order_id);
        let exposure = order.exposure_f64();

        assert_eq!(exposure, price.as_f64() * size.as_f64());
    }

    #[test]
    fn test_signed_size() {
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let order_id = 123456;

        let order_buy = BookOrder::new(OrderSide::Buy, price.clone(), size.clone(), order_id);
        let signed_size_buy = order_buy.signed_size_f64();
        assert_eq!(signed_size_buy, size.as_f64());

        let order_sell = BookOrder::new(OrderSide::Sell, price.clone(), size.clone(), order_id);
        let signed_size_sell = order_sell.signed_size_f64();
        assert_eq!(signed_size_sell, -(size.as_f64()));
    }

    #[test]
    fn test_display() {
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;

        let order = BookOrder::new(side, price.clone(), size.clone(), order_id);
        let display = format!("{}", order);

        let expected = format!("{},{},{},{}", price, size, side, order_id);
        assert_eq!(display, expected);
    }

    #[rstest(side, case(OrderSide::Buy), case(OrderSide::Sell))]
    fn test_from_quote_tick(side: OrderSide) {
        let tick = QuoteTick::new(
            InstrumentId::from_str("ETHUSDT-PERP.BINANCE").unwrap(),
            Price::new(5000.0, 2),
            Price::new(5001.0, 2),
            Quantity::new(100.0, 3),
            Quantity::new(99.0, 3),
            0,
            0,
        );

        let book_order = BookOrder::from_quote_tick(&tick, side.clone());

        assert_eq!(book_order.side, side);
        assert_eq!(
            book_order.price,
            match side {
                OrderSide::Buy => tick.bid,
                OrderSide::Sell => tick.ask,
                _ => panic!("Invalid test"),
            }
        );
        assert_eq!(
            book_order.size,
            match side {
                OrderSide::Buy => tick.bid_size,
                OrderSide::Sell => tick.ask_size,
                _ => panic!("Invalid test"),
            }
        );
        assert_eq!(
            book_order.order_id,
            match side {
                OrderSide::Buy => tick.bid.raw as u64,
                OrderSide::Sell => tick.ask.raw as u64,
                _ => panic!("Invalid test"),
            }
        );
    }

    #[rstest(side, case(OrderSide::Buy), case(OrderSide::Sell))]
    fn test_from_trade_tick(side: OrderSide) {
        let tick = TradeTick::new(
            InstrumentId::from_str("ETHUSDT-PERP.BINANCE").unwrap(),
            Price::new(5000.0, 2),
            Quantity::new(100.0, 2),
            AggressorSide::Buyer,
            TradeId::new("1"),
            0,
            0,
        );

        let book_order = BookOrder::from_trade_tick(&tick, side);

        assert_eq!(book_order.side, side);
        assert_eq!(book_order.price, tick.price);
        assert_eq!(book_order.size, tick.size);
        assert_eq!(book_order.order_id, tick.price.raw as u64);
    }

    #[test]
    fn test_to_dict_and_from_dict() {
        pyo3::prepare_freethreaded_python();

        let order = create_stub_book_order();

        Python::with_gil(|py| {
            let dict = order.as_dict();
            let parsed = BookOrder::from_dict(dict.as_ref(py)).unwrap();
            assert_eq!(parsed, order);
        });
    }

    #[test]
    fn test_json_serialization() {
        let order = create_stub_book_order();
        let serialized = order.as_json_bytes().unwrap();
        let deserialized = BookOrder::from_json_bytes(serialized).unwrap();
        assert_eq!(deserialized, order);
    }

    #[test]
    fn test_msgpack_serialization() {
        let order = create_stub_book_order();
        let serialized = order.as_msgpack_bytes().unwrap();
        let deserialized = BookOrder::from_msgpack_bytes(serialized).unwrap();
        assert_eq!(deserialized, order);
    }
}
