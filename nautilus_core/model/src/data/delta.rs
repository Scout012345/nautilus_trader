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
    collections::{hash_map::DefaultHasher, HashMap},
    fmt::{Display, Formatter},
    hash::{Hash, Hasher},
    str::FromStr,
};

use nautilus_core::{serialization::Serializable, time::UnixNanos};
use pyo3::{exceptions::PyValueError, prelude::*, pyclass::CompareOp, types::PyDict};
use serde::{Deserialize, Serialize};

use super::order::{BookOrder, NULL_ORDER};
use crate::{
    enums::{BookAction, FromU8, OrderSide},
    identifiers::instrument_id::InstrumentId,
    types::{price::Price, quantity::Quantity},
};

/// Represents a single change/delta in an order book.
#[repr(C)]
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(tag = "type")]
#[pyclass]
pub struct OrderBookDelta {
    /// The instrument ID for the book.
    pub instrument_id: InstrumentId,
    /// The order book delta action.
    pub action: BookAction,
    /// The order to apply.
    pub order: BookOrder,
    /// A combination of packet end with matching engine status.
    pub flags: u8,
    /// The message sequence number assigned at the venue.
    pub sequence: u64,
    /// The UNIX timestamp (nanoseconds) when the data event occurred.
    pub ts_event: UnixNanos,
    /// The UNIX timestamp (nanoseconds) when the data object was initialized.
    pub ts_init: UnixNanos,
}

impl OrderBookDelta {
    #[allow(clippy::too_many_arguments)]
    #[must_use]
    pub fn new(
        instrument_id: InstrumentId,
        action: BookAction,
        order: BookOrder,
        flags: u8,
        sequence: u64,
        ts_event: UnixNanos,
        ts_init: UnixNanos,
    ) -> Self {
        Self {
            instrument_id,
            action,
            order,
            flags,
            sequence,
            ts_event,
            ts_init,
        }
    }

    pub fn get_metadata(
        instrument_id: &InstrumentId,
        price_precision: u8,
        size_precision: u8,
    ) -> HashMap<String, String> {
        let mut metadata = HashMap::new();
        metadata.insert("instrument_id".to_string(), instrument_id.to_string());
        metadata.insert("price_precision".to_string(), price_precision.to_string());
        metadata.insert("size_precision".to_string(), size_precision.to_string());
        metadata
    }

    pub fn from_pyobject(obj: &PyAny) -> PyResult<Self> {
        let instrument_id_obj: &PyAny = obj.getattr("instrument_id")?.extract()?;
        let instrument_id_str = instrument_id_obj.getattr("value")?.extract()?;
        let instrument_id = InstrumentId::from_str(instrument_id_str)
            .map_err(|e| PyValueError::new_err(format!("{}", e)))
            .unwrap();

        let action_obj: &PyAny = obj.getattr("action")?.extract()?;
        let action_u8 = action_obj.getattr("value")?.extract()?;
        let action = BookAction::from_u8(action_u8).unwrap();

        let flags: u8 = obj.getattr("flags")?.extract()?;
        let sequence: u64 = obj.getattr("sequence")?.extract()?;
        let ts_event: UnixNanos = obj.getattr("ts_event")?.extract()?;
        let ts_init: UnixNanos = obj.getattr("ts_init")?.extract()?;

        let order_pyobject = obj.getattr("order")?;
        let order: BookOrder = if order_pyobject.is_none() {
            NULL_ORDER
        } else {
            let side_obj: &PyAny = order_pyobject.getattr("side")?.extract()?;
            let side_u8 = side_obj.getattr("value")?.extract()?;
            let side = OrderSide::from_u8(side_u8).unwrap();

            let price_py: &PyAny = order_pyobject.getattr("price")?;
            let price_f64: f64 = price_py.call_method0("as_double")?.extract()?;
            let price_prec: u8 = price_py.getattr("precision")?.extract()?;
            let price = Price::new(price_f64, price_prec);

            let size_py: &PyAny = order_pyobject.getattr("price")?;
            let size_f64: f64 = size_py.call_method0("as_double")?.extract()?;
            let size_prec: u8 = size_py.getattr("precision")?.extract()?;
            let size = Quantity::new(size_f64, size_prec);

            let order_id: u64 = order_pyobject.getattr("order_id")?.extract()?;
            BookOrder {
                side,
                price,
                size,
                order_id,
            }
        };

        Ok(Self::new(
            instrument_id,
            action,
            order,
            flags,
            sequence,
            ts_event,
            ts_init,
        ))
    }
}

impl Serializable for OrderBookDelta {}

impl Display for OrderBookDelta {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{},{},{},{},{},{},{}",
            self.instrument_id,
            self.action,
            self.order,
            self.flags,
            self.sequence,
            self.ts_event,
            self.ts_init
        )
    }
}

#[pymethods]
impl OrderBookDelta {
    #[new]
    fn py_new(
        instrument_id: InstrumentId,
        action: BookAction,
        order: BookOrder,
        flags: u8,
        sequence: u64,
        ts_event: UnixNanos,
        ts_init: UnixNanos,
    ) -> Self {
        Self::new(
            instrument_id,
            action,
            order,
            flags,
            sequence,
            ts_event,
            ts_init,
        )
    }

    fn __richcmp__(&self, other: &Self, op: CompareOp, py: Python<'_>) -> Py<PyAny> {
        match op {
            CompareOp::Eq => self.eq(other).into_py(py),
            CompareOp::Ne => self.ne(other).into_py(py),
            _ => py.NotImplemented(),
        }
    }

    fn __hash__(&self) -> isize {
        let mut h = DefaultHasher::new();
        self.hash(&mut h);
        h.finish() as isize
    }

    fn __str__(&self) -> String {
        self.to_string()
    }

    fn __repr__(&self) -> String {
        format!("{self:?}")
    }

    #[getter]
    fn instrument_id(&self) -> InstrumentId {
        self.instrument_id
    }

    #[getter]
    fn action(&self) -> BookAction {
        self.action
    }

    #[getter]
    fn order(&self) -> BookOrder {
        self.order
    }

    #[getter]
    fn flags(&self) -> u8 {
        self.flags
    }

    #[getter]
    fn sequence(&self) -> u64 {
        self.sequence
    }

    #[getter]
    fn ts_event(&self) -> UnixNanos {
        self.ts_event
    }

    #[getter]
    fn ts_init(&self) -> UnixNanos {
        self.ts_init
    }

    /// Return a dictionary representation of the object.
    pub fn as_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        // Serialize object to JSON bytes
        let json_str =
            serde_json::to_string(self).map_err(|e| PyValueError::new_err(e.to_string()))?;
        // Parse JSON into a Python dictionary
        let py_dict: Py<PyDict> = PyModule::import(py, "msgspec")?
            .getattr("json")?
            .call_method("decode", (json_str,), None)?
            .extract()?;
        Ok(py_dict)
    }

    /// Return a new object from the given dictionary representation.
    #[staticmethod]
    pub fn from_dict(py: Python<'_>, values: Py<PyDict>) -> PyResult<Self> {
        // Serialize to JSON bytes
        let json_bytes: Vec<u8> = PyModule::import(py, "msgspec")?
            .getattr("json")?
            .call_method("encode", (values,), None)?
            .extract()?;
        // Deserialize to object
        let instance = serde_json::from_slice(&json_bytes)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(instance)
    }

    #[staticmethod]
    fn from_json(data: Vec<u8>) -> PyResult<Self> {
        Self::from_json_bytes(data).map_err(|e| PyValueError::new_err(e.to_string()))
    }

    #[staticmethod]
    fn from_msgpack(data: Vec<u8>) -> PyResult<Self> {
        Self::from_msgpack_bytes(data).map_err(|e| PyValueError::new_err(e.to_string()))
    }

    /// Return JSON encoded bytes representation of the object.
    fn as_json(&self, py: Python<'_>) -> Py<PyAny> {
        // Unwrapping is safe when serializing a valid object
        self.as_json_bytes().unwrap().into_py(py)
    }

    /// Return MsgPack encoded bytes representation of the object.
    fn as_msgpack(&self, py: Python<'_>) -> Py<PyAny> {
        // Unwrapping is safe when serializing a valid object
        self.as_msgpack_bytes().unwrap().into_py(py)
    }
}

////////////////////////////////////////////////////////////////////////////////
// Tests
////////////////////////////////////////////////////////////////////////////////

#[cfg(test)]
mod tests {
    use std::str::FromStr;

    use super::*;
    use crate::{
        enums::OrderSide,
        types::{price::Price, quantity::Quantity},
    };

    fn create_stub_delta() -> OrderBookDelta {
        let instrument_id = InstrumentId::from_str("AAPL.NASDAQ").unwrap();
        let action = BookAction::Add;
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;
        let flags = 0;
        let sequence = 1;
        let ts_event = 1;
        let ts_init = 2;

        let order = BookOrder::new(side, price.clone(), size.clone(), order_id);
        OrderBookDelta::new(
            instrument_id.clone(),
            action,
            order,
            flags,
            sequence,
            ts_event,
            ts_init,
        )
    }

    #[test]
    fn test_new() {
        let instrument_id = InstrumentId::from_str("AAPL.NASDAQ").unwrap();
        let action = BookAction::Add;
        let price = Price::from("100.00");
        let size = Quantity::from("10");
        let side = OrderSide::Buy;
        let order_id = 123456;
        let flags = 0;
        let sequence = 1;
        let ts_event = 1;
        let ts_init = 2;

        let order = BookOrder::new(side, price.clone(), size.clone(), order_id);

        let delta = OrderBookDelta::new(
            instrument_id.clone(),
            action,
            order.clone(),
            flags,
            sequence,
            ts_event,
            ts_init,
        );

        assert_eq!(delta.instrument_id, instrument_id);
        assert_eq!(delta.action, action);
        assert_eq!(delta.order.price, price);
        assert_eq!(delta.order.size, size);
        assert_eq!(delta.order.side, side);
        assert_eq!(delta.order.order_id, order_id);
        assert_eq!(delta.flags, flags);
        assert_eq!(delta.sequence, sequence);
        assert_eq!(delta.ts_event, ts_event);
        assert_eq!(delta.ts_init, ts_init);
    }

    #[test]
    fn test_display() {
        let delta = create_stub_delta();
        assert_eq!(
            format!("{}", delta),
            "AAPL.NASDAQ,ADD,100.00,10,BUY,123456,0,1,1,2".to_string()
        );
    }

    #[test]
    fn test_as_dict() {
        pyo3::prepare_freethreaded_python();

        let delta = create_stub_delta();

        Python::with_gil(|py| {
            let dict_string = delta.as_dict(py).unwrap().to_string();
            let expected_string = r#"{'type': 'OrderBookDelta', 'instrument_id': 'AAPL.NASDAQ', 'action': 'ADD', 'order': {'side': 'BUY', 'price': '100.00', 'size': '10', 'order_id': 123456}, 'flags': 0, 'sequence': 1, 'ts_event': 1, 'ts_init': 2}"#;
            assert_eq!(dict_string, expected_string);
        });
    }

    #[test]
    fn test_from_dict() {
        pyo3::prepare_freethreaded_python();

        let delta = create_stub_delta();

        Python::with_gil(|py| {
            let dict = delta.as_dict(py).unwrap();
            let parsed = OrderBookDelta::from_dict(py, dict).unwrap();
            assert_eq!(parsed, delta);
        });
    }

    #[test]
    fn test_json_serialization() {
        let delta = create_stub_delta();
        let serialized = delta.as_json_bytes().unwrap();
        let deserialized = OrderBookDelta::from_json_bytes(serialized).unwrap();
        assert_eq!(deserialized, delta);
    }

    #[test]
    fn test_msgpack_serialization() {
        let delta = create_stub_delta();
        let serialized = delta.as_msgpack_bytes().unwrap();
        let deserialized = OrderBookDelta::from_msgpack_bytes(serialized).unwrap();
        assert_eq!(deserialized, delta);
    }

    #[test]
    fn test_from_pyobject() {
        let delta = create_stub_delta();

        Python::with_gil(|py| {
            let delta_pyobject = delta.into_py(py);
            let parsed_delta = OrderBookDelta::from_pyobject(delta_pyobject.as_ref(py)).unwrap();
            assert_eq!(parsed_delta, delta);
        });
    }
}
