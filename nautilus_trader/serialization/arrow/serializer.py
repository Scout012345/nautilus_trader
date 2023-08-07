# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2023 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------
from io import BytesIO
from typing import Any, Callable, Optional, Union

import pyarrow as pa

from nautilus_trader.core.correctness import PyCondition
from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.core.nautilus_pyo3.persistence import DataTransformer
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.data.base import GenericData
from nautilus_trader.persistence.wranglers_v2 import BarDataWrangler
from nautilus_trader.persistence.wranglers_v2 import OrderBookDeltaDataWrangler
from nautilus_trader.persistence.wranglers_v2 import QuoteTickDataWrangler
from nautilus_trader.persistence.wranglers_v2 import TradeTickDataWrangler
from nautilus_trader.serialization.arrow.schema import NAUTILUS_ARROW_SCHEMA


_ARROW_SERIALIZER: dict[type, Callable] = {}
_ARROW_DESERIALIZER: dict[type, Callable] = {}
_SCHEMAS: dict[type, pa.Schema] = {}

DATA_OR_EVENTS = Union[Data, Event]


def get_schema(cls: type):
    return _SCHEMAS[cls]


def list_schemas():
    return _SCHEMAS


def _clear_all(**kwargs):
    # Used for testing
    global _CLS_TO_TABLE, _SCHEMAS, _PARTITION_KEYS, _CHUNK
    if kwargs.get("force", False):
        _PARTITION_KEYS = {}
        _SCHEMAS = {}
        _CLS_TO_TABLE = {}  # type: dict[type, type]
        _CHUNK = set()


def register_arrow(
    cls: type,
    schema: Optional[pa.Schema],
    serializer: Optional[Callable],
    deserializer: Optional[Callable] = None,
):
    """
    Register a new class for serialization to parquet.

    Parameters
    ----------
    cls : type
        The type to register serialization for.
    serializer : Callable, optional
        The callable to serialize instances of type `cls_type` to something
        parquet can write.
    deserializer : Callable, optional
        The callable to deserialize rows from parquet into `cls_type`.
    schema : pa.Schema, optional
        If the schema cannot be correctly inferred from a subset of the data
        (i.e. if certain values may be missing in the first chunk).
    table : type, optional
        An optional table override for `cls`. Used if `cls` is going to be
        transformed and stored in a table other than
        its own.

    """
    PyCondition.type(schema, pa.Schema, "schema")
    PyCondition.type(serializer, Callable, "serializer")
    PyCondition.type_or_none(deserializer, Callable, "deserializer")

    if serializer is not None:
        _ARROW_SERIALIZER[cls] = serializer
    if deserializer is not None:
        _ARROW_DESERIALIZER[cls] = deserializer
    if schema is not None:
        _SCHEMAS[cls] = schema


class ArrowSerializer:
    """
    Serialize nautilus objects to arrow RecordBatches.
    """

    @staticmethod
    def _unpack_container_objects(cls: type, data: list[Any]):
        if cls == OrderBookDeltas:
            return [delta for deltas in data for delta in deltas.deltas]
        return data

    @staticmethod
    def rust_objects_to_record_batch(data: list[Data], cls: type) -> pa.RecordBatch:
        processed = ArrowSerializer._unpack_container_objects(cls, data)
        batches_bytes = DataTransformer.pyobjects_to_batches_bytes(processed)
        reader = pa.ipc.open_stream(BytesIO(batches_bytes))
        table: pa.Table = reader.read_all()
        batches = table.to_batches()
        assert len(batches) == 1, len(batches)
        return batches[0]

    @staticmethod
    def serialize(
        data: DATA_OR_EVENTS,
        cls: Optional[type[DATA_OR_EVENTS]] = None,
    ) -> pa.RecordBatch:
        if isinstance(data, GenericData):
            data = data.data
        cls = cls or type(data)
        delegate = _ARROW_DESERIALIZER.get(cls)
        if delegate is None:
            if cls in RUST_SERIALIZERS:
                return ArrowSerializer.rust_objects_to_record_batch([data], cls=cls)
            raise TypeError(
                f"Cannot serialize object `{cls}`. Register a "
                f"serialization method via `nautilus_trader.persistence.catalog.parquet.serializers.register_parquet()`",
            )

        batch = delegate(data)
        assert isinstance(batch, pa.RecordBatch)
        return batch

    @staticmethod
    def serialize_batch(data: list[DATA_OR_EVENTS], cls: type[DATA_OR_EVENTS]) -> pa.RecordBatch:
        """
        Serialize the given instrument to `Parquet` specification bytes.

        Parameters
        ----------
        data : list[Any]
            The object to serialize.
        cls: type
            The class of the data

        Returns
        -------
        bytes

        Raises
        ------
        TypeError
            If `obj` cannot be serialized.

        """
        if cls in RUST_SERIALIZERS:
            return ArrowSerializer.rust_objects_to_record_batch(data, cls=cls)
        batches = [ArrowSerializer.serialize(obj, cls) for obj in data]
        return pa.Table.from_batches(batches, schema=batches[0].schema)

    @staticmethod
    def deserialize(cls: type, batch: Union[pa.RecordBatch, pa.Table]):
        """
        Deserialize the given `Parquet` specification bytes to an object.

        Parameters
        ----------
        cls : type
            The type to deserialize to.
        batch : pyarrow.RecordBatch
            The RecordBatch to deserialize.

        Returns
        -------
        object

        Raises
        ------
        TypeError
            If `chunk` cannot be deserialized.

        """
        delegate = _ARROW_DESERIALIZER.get(cls)
        if delegate is None:
            if cls in RUST_SERIALIZERS:
                return ArrowSerializer.deserialize_rust(cls=cls, batch=batch)
            raise TypeError(
                f"Cannot deserialize object `{cls}`. Register a "
                f"deserialization method via `arrow.serializer.register_parquet()`",
            )

        return delegate(batch)

    @staticmethod
    def deserialize_rust(cls, batch: pa.RecordBatch) -> list[DATA_OR_EVENTS]:
        Wrangler = {
            QuoteTick: QuoteTickDataWrangler,
            TradeTick: TradeTickDataWrangler,
            Bar: BarDataWrangler,
            OrderBookDelta: OrderBookDeltaDataWrangler,
        }[cls]
        wrangler = Wrangler.from_schema(batch.schema)
        ticks = wrangler.from_arrow(pa.Table.from_batches([batch]))
        return ticks


def make_dict_serializer(schema: pa.Schema):
    def inner(data: list[DATA_OR_EVENTS]):
        if not isinstance(data, list):
            data = [data]
        dicts = [d.to_dict(d) for d in data]
        return dicts_to_record_batch(dicts, schema=schema)

    return inner


def make_dict_deserializer(cls):
    def inner(table: pa.Table) -> list[DATA_OR_EVENTS]:
        assert isinstance(table, pa.Table)
        return [cls.from_dict(d) for d in table.to_pylist()]

    return inner


def dicts_to_record_batch(data: list[dict], schema: pa.Schema) -> pa.RecordBatch:
    return pa.RecordBatch.from_pylist(data, schema=schema)


RUST_SERIALIZERS = {
    QuoteTick,
    TradeTick,
    Bar,
    OrderBookDelta,
    OrderBookDeltas,
}

# Check we have each type defined only once (rust or python)
assert not set(NAUTILUS_ARROW_SCHEMA).intersection(RUST_SERIALIZERS)
assert not RUST_SERIALIZERS.intersection(set(NAUTILUS_ARROW_SCHEMA))

for _cls in NAUTILUS_ARROW_SCHEMA:
    register_arrow(
        cls=_cls,
        schema=NAUTILUS_ARROW_SCHEMA[_cls],
        serializer=make_dict_serializer(NAUTILUS_ARROW_SCHEMA[_cls]),
        deserializer=make_dict_deserializer(_cls),
    )
