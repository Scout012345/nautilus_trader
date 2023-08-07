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

import os
import pathlib
import platform
from io import BytesIO
from itertools import groupby
from pathlib import Path
from typing import Any, Callable, Optional, Union

import fsspec
import pandas as pd
import pyarrow as pa
import pyarrow.dataset
import pyarrow.dataset as pds
from fsspec.implementations.local import make_path_posix
from fsspec.implementations.memory import MemoryFileSystem
from fsspec.utils import infer_storage_options
from pyarrow import ArrowInvalid

from nautilus_trader.core.data import Data
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.core.inspect import is_nautilus_class
from nautilus_trader.core.message import Event
from nautilus_trader.core.nautilus_pyo3.persistence import DataBackendSession
from nautilus_trader.core.nautilus_pyo3.persistence import DataTransformer
from nautilus_trader.core.nautilus_pyo3.persistence import NautilusDataType
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import DataType
from nautilus_trader.model.data import GenericData
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.data.book import OrderBookDelta
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.persistence.catalog.base import BaseDataCatalog
from nautilus_trader.persistence.catalog.parquet.util import camel_to_snake_case
from nautilus_trader.persistence.catalog.parquet.util import class_to_filename
from nautilus_trader.persistence.wranglers import list_from_capsule
from nautilus_trader.serialization.arrow.serializer import RUST_SERIALIZERS
from nautilus_trader.serialization.arrow.serializer import ArrowSerializer
from nautilus_trader.serialization.arrow.serializer import list_schemas


timestamp_like = Union[int, str, float]


class ParquetDataCatalog(BaseDataCatalog):
    """
    Provides a queryable data catalog persisted to files in parquet format.

    Parameters
    ----------
    path : str
        The root path for this data catalog. Must exist and must be an absolute path.
    fs_protocol : str, default 'file'
        The fsspec filesystem protocol to use.
    fs_storage_options : dict, optional
        The fs storage options.

    Warnings
    --------
    The catalog is not threadsafe.

    """

    def __init__(
        self,
        path: str,
        fs_protocol: Optional[str] = "file",
        fs_storage_options: Optional[dict] = None,
        dataset_kwargs: Optional[dict] = None,
    ):
        self.fs_protocol = fs_protocol
        self.fs_storage_options = fs_storage_options or {}
        self.fs: fsspec.AbstractFileSystem = fsspec.filesystem(
            self.fs_protocol,
            **self.fs_storage_options,
        )
        self.serializer = ArrowSerializer()
        self.dataset_kwargs = dataset_kwargs or {}

        path = make_path_posix(str(path))

        if (
            isinstance(self.fs, MemoryFileSystem)
            and platform.system() == "Windows"
            and not path.startswith("/")
        ):
            path = "/" + path

        self.path = str(path)

    @classmethod
    def from_env(cls):
        return cls.from_uri(os.environ["NAUTILUS_PATH"] + "/catalog")

    @classmethod
    def from_uri(cls, uri):
        if "://" not in uri:
            # Assume a local path
            uri = "file://" + uri
        parsed = infer_storage_options(uri)
        path = parsed.pop("path")
        protocol = parsed.pop("protocol")
        storage_options = parsed.copy()
        return cls(path=path, fs_protocol=protocol, fs_storage_options=storage_options)

    # -- WRITING -----------------------------------------------------------------------------------
    def objects_to_rust_table(self, data: list[Data], cls: type) -> pa.Table:
        processed = self._unpack_container_objects(cls, data)
        batches_bytes = DataTransformer.pyobjects_to_batches_bytes(processed)
        batches_stream = BytesIO(batches_bytes)
        reader = pa.ipc.open_stream(batches_stream)
        return reader.read_all()

    def _unpack_container_objects(self, cls: type, data: list[Any]):
        if cls == OrderBookDeltas:
            return [delta for deltas in data for delta in deltas.deltas]
        return data

    def _objects_to_table(self, data: list[Data], cls: type) -> pa.Table:
        assert len(data) > 0
        assert all(type(obj) is cls for obj in data)  # same type

        if cls in RUST_SERIALIZERS:
            table = self.objects_to_rust_table(data, cls=cls)
        else:
            table = self.serializer.serialize_batch(data, cls=cls)
        assert table is not None
        return table

    def _make_path(self, cls: type[Data], instrument_id: Optional[str] = None) -> str:
        if instrument_id is not None:
            return f"{self.path}/data/{class_to_filename(cls)}/{instrument_id}"
        else:
            return f"{self.path}/data/{class_to_filename(cls)}"

    def write_chunk(
        self,
        data: list[Data],
        cls: type[Data],
        instrument_id: Optional[str] = None,
        **kwargs,
    ):
        table = self._objects_to_table(data, cls=cls)

        # Make base path
        path = self._make_path(cls=cls, instrument_id=instrument_id)

        # Write parquet file
        pyarrow.dataset.write_dataset(
            data=table,
            base_dir=path,
            format="parquet",
            filesystem=self.fs,
            **self.dataset_kwargs,
            **kwargs,
        )

    def write_data(self, data: list[Union[Data, Event]], **kwargs):
        def key(obj) -> tuple[str, Optional[str]]:
            name = type(obj).__name__
            if isinstance(obj, Instrument):
                return name, obj.id
            elif hasattr(obj, "instrument_id"):
                return name, obj.instrument_id
            return name, None

        name_to_cls = {cls.__name__: cls for cls in {type(d) for d in data}}
        for (cls_name, instrument_id), single_type in groupby(sorted(data, key=key), key=key):
            self.write_chunk(
                data=list(single_type),
                cls=name_to_cls[cls_name],
                instrument_id=instrument_id,
                **kwargs,
            )

    # -- QUERIES -----------------------------------------------------------------------------------

    def query_rust(
        self,
        cls,
        instrument_ids=None,
        start: Optional[timestamp_like] = None,
        end: Optional[timestamp_like] = None,
        where: Optional[str] = None,
        **kwargs,
    ):
        name = cls.__name__
        file_prefix = class_to_filename(cls)
        data_type = getattr(NautilusDataType, {"OrderBookDeltas": "OrderBookDelta"}.get(name, name))
        session = DataBackendSession()
        # TODO (bm) - fix this glob, query once on catalog creation?
        for idx, fn in enumerate(self.fs.glob(f"{self.path}/data/{file_prefix}/**/*")):
            assert pathlib.Path(fn).exists()
            if instrument_ids and not any(id_ in fn for id_ in instrument_ids):
                continue
            table = f"{file_prefix}_{idx}"
            query = self._build_query(
                table,
                instrument_ids=None,
                start=start,
                end=end,
                where=where,
            )
            session.add_file_with_query(table, fn, query, data_type)

        result = session.to_query_result()

        # Gather data
        data = []
        for chunk in result:
            data.extend(list_from_capsule(chunk))
        return data

    def query_pyarrow(
        self,
        cls,
        instrument_ids=None,
        start: Optional[timestamp_like] = None,
        end: Optional[timestamp_like] = None,
        where: Optional[str] = None,
        **kwargs,
    ):
        file_prefix = class_to_filename(cls)
        dataset_path = f"{self.path}/data/{file_prefix}"
        if not self.fs.exists(dataset_path):
            return
        dataset = pds.dataset(dataset_path)
        table = dataset.to_table()
        return self._handle_table_nautilus(table, cls=cls)

    def query(
        self,
        cls,
        instrument_ids=None,
        start: Optional[timestamp_like] = None,
        end: Optional[timestamp_like] = None,
        where: Optional[str] = None,
        **kwargs,
    ):
        if cls in (QuoteTick, TradeTick, Bar, OrderBookDelta):
            data = self.query_rust(
                cls=cls,
                instrument_ids=instrument_ids,
                start=start,
                end=end,
                where=where,
                **kwargs,
            )
        else:
            data = self.query_pyarrow(
                cls=cls,
                instrument_ids=instrument_ids,
                start=start,
                end=end,
                where=where,
                **kwargs,
            )

        if not is_nautilus_class(cls):
            # Special handling for generic data
            data = [
                GenericData(data_type=DataType(cls, metadata=kwargs.get("metadata")), data=d)
                for d in data
            ]
        return data

    def _build_query(
        self,
        table: str,
        instrument_ids=None,
        start: Optional[timestamp_like] = None,
        end: Optional[timestamp_like] = None,
        where: Optional[str] = None,
    ) -> str:
        """
        Build datafusion sql query.
        """
        q = f"SELECT * FROM {table}"  # noqa
        conditions: list[str] = [] + ([where] if where else [])
        if len(instrument_ids or []) == 1:
            conditions.append(f"instrument_id = '{instrument_ids[0]}'")
        elif instrument_ids:
            conditions.append(f"instrument_id in {tuple(instrument_ids)}")
        if start:
            start_ts = dt_to_unix_nanos(pd.Timestamp(start))
            conditions.append(f"ts_init >= {start_ts}")
        if end:
            end_ts = dt_to_unix_nanos(pd.Timestamp(end))
            conditions.append(f"ts_init <= {end_ts}")
        if conditions:
            q += f" WHERE {' AND '.join(conditions)}"
        q += " ORDER BY ts_init"
        return q

    @staticmethod
    def _handle_table_nautilus(
        table: Union[pa.Table, pd.DataFrame],
        cls: type,
    ):
        data = ArrowSerializer.deserialize(cls=cls, table=table)
        return data

    def _query_subclasses(
        self,
        base_cls: type,
        instrument_ids: Optional[list[str]] = None,
        filter_expr: Optional[Callable] = None,
        **kwargs,
    ):
        subclasses = [base_cls, *base_cls.__subclasses__()]

        dfs = []
        for cls in subclasses:
            try:
                df = self.query(
                    cls=cls,
                    filter_expr=filter_expr,
                    instrument_ids=instrument_ids,
                    raise_on_empty=False,
                    **kwargs,
                )
                dfs.append(df)
            except ArrowInvalid as e:
                # If we're using a `filter_expr` here, there's a good chance
                # this error is using a filter that is specific to one set of
                # instruments and not to others, so we ignore it (if not; raise).
                if filter_expr is not None:
                    continue
                else:
                    raise e

        objects = [o for objs in [df for df in dfs if df is not None] for o in objs]
        return objects

    # ---  OVERLOADED BASE METHODS ------------------------------------------------
    def instruments(
        self,
        instrument_type: Optional[type] = None,
        instrument_ids: Optional[list[str]] = None,
        **kwargs,
    ):
        return super().instruments(
            instrument_type=instrument_type,
            instrument_ids=instrument_ids,
            **kwargs,
        )

    def list_data_types(self):
        glob_path = f"{self.path}/data/*"
        return [pathlib.Path(p).stem for p in self.fs.glob(glob_path)]

    def list_backtest_runs(self) -> list[str]:
        glob_path = f"{self.path}/backtest/*.feather"
        return [p.stem for p in map(Path, self.fs.glob(glob_path))]

    def list_live_runs(self) -> list[str]:
        glob_path = f"{self.path}/live/*.feather"
        return [p.stem for p in map(Path, self.fs.glob(glob_path))]

    def read_live_run(self, instance_id: str, **kwargs):
        return self._read_feather(kind="live", instance_id=instance_id, **kwargs)

    def read_backtest(self, instance_id: str, **kwargs):
        return self._read_feather(kind="backtest", instance_id=instance_id, **kwargs)

    def _read_feather(self, kind: str, instance_id: str, raise_on_failed_deserialize: bool = False):
        class_mapping: dict[str, type] = {class_to_filename(cls): cls for cls in list_schemas()}
        data = {}
        glob_path = f"{self.path}/{kind}/{instance_id}.feather/*.feather"

        for path in list(self.fs.glob(glob_path)):
            cls_name = camel_to_snake_case(pathlib.Path(path).stem).replace("__", "_")
            df = read_feather_file(path=path, fs=self.fs)

            if df is None:
                print(f"No data for {cls_name}")
                continue
            # Apply post read fixes
            try:
                objs = self._handle_table_nautilus(
                    table=pa.Table.from_pandas(df),
                    cls=class_mapping[cls_name],
                )
                data[cls_name] = objs
            except Exception as e:
                if raise_on_failed_deserialize:
                    raise
                print(f"Failed to deserialize {cls_name}: {e}")
        return sorted(sum(data.values(), []), key=lambda x: x.ts_init)


def read_feather_file(path: str, fs: Optional[fsspec.AbstractFileSystem] = None):
    fs = fs or fsspec.filesystem("file")
    if not fs.exists(path):
        return
    try:
        with fs.open(path) as f:
            reader = pa.ipc.open_stream(f)
            return reader.read_pandas()
    except (pa.ArrowInvalid, FileNotFoundError):
        return
