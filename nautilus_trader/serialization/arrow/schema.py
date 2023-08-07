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

import msgspec
import pyarrow as pa

from nautilus_trader.adapters.binance.common.types import BinanceBar
from nautilus_trader.common.messages import ComponentStateChanged
from nautilus_trader.common.messages import TradingStateChanged
from nautilus_trader.model.data import InstrumentClose
from nautilus_trader.model.data import InstrumentStatusUpdate
from nautilus_trader.model.data import Ticker
from nautilus_trader.model.data import VenueStatusUpdate
from nautilus_trader.model.events import OrderAccepted
from nautilus_trader.model.events import OrderCanceled
from nautilus_trader.model.events import OrderCancelRejected
from nautilus_trader.model.events import OrderDenied
from nautilus_trader.model.events import OrderExpired
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.events import OrderInitialized
from nautilus_trader.model.events import OrderModifyRejected
from nautilus_trader.model.events import OrderPendingCancel
from nautilus_trader.model.events import OrderPendingUpdate
from nautilus_trader.model.events import OrderRejected
from nautilus_trader.model.events import OrderSubmitted
from nautilus_trader.model.events import OrderTriggered
from nautilus_trader.model.events import OrderUpdated


# TODO; Should all move down to rust


NAUTILUS_ARROW_SCHEMA = {
    Ticker: pa.schema(
        {
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
        metadata={"type": "Ticker"},
    ),
    VenueStatusUpdate: pa.schema(
        {
            "venue": pa.dictionary(pa.int16(), pa.string()),
            "status": pa.dictionary(pa.int8(), pa.string()),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
        metadata={"type": "InstrumentStatusUpdate"},
    ),
    InstrumentClose: pa.schema(
        {
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "close_type": pa.dictionary(pa.int8(), pa.string()),
            "close_price": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
        metadata={"type": "InstrumentClose"},
    ),
    InstrumentStatusUpdate: pa.schema(
        {
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "status": pa.dictionary(pa.int8(), pa.string()),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
        metadata={"type": "InstrumentStatusUpdate"},
    ),
    ComponentStateChanged: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "component_id": pa.dictionary(pa.int16(), pa.string()),
            "component_type": pa.dictionary(pa.int8(), pa.string()),
            "state": pa.string(),
            "config": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
        metadata={"type": "ComponentStateChanged"},
    ),
    TradingStateChanged: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "state": pa.string(),
            "config": pa.binary(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
        metadata={"type": "TradingStateChanged"},
    ),
    OrderInitialized: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "order_side": pa.dictionary(pa.int8(), pa.string()),
            "order_type": pa.dictionary(pa.int8(), pa.string()),
            "quantity": pa.float64(),
            "time_in_force": pa.dictionary(pa.int8(), pa.string()),
            "post_only": pa.bool_(),
            "reduce_only": pa.bool_(),
            # -- Options fields -- #
            "price": pa.float64(),
            "trigger_price": pa.string(),
            "trigger_type": pa.dictionary(pa.int8(), pa.string()),
            "limit_offset": pa.string(),
            "trailing_offset": pa.string(),
            "trailing_offset_type": pa.dictionary(pa.int8(), pa.string()),
            "expire_time_ns": pa.uint64(),
            "display_qty": pa.string(),
            # --------------------- #
            "emulation_trigger": pa.string(),
            "contingency_type": pa.string(),
            "order_list_id": pa.string(),
            "linked_order_ids": pa.string(),
            "parent_order_id": pa.string(),
            "exec_algorithm_id": pa.string(),
            "exec_algorithm_params": pa.binary(),
            "exec_spawn_id": pa.binary(),
            "tags": pa.string(),
            "event_id": pa.string(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
        metadata={
            "options_fields": msgspec.json.encode(
                [
                    "price",
                    "trigger_price",
                    "trigger_type",
                    "limit_offset",
                    "trailing_offset",
                    "trailing_offset_type",
                    "display_qty",
                    "expire_time_ns",
                ],
            ),
        },
    ),
    OrderDenied: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "reason": pa.dictionary(pa.int16(), pa.string()),
            "event_id": pa.string(),
            "ts_init": pa.uint64(),
        },
    ),
    OrderSubmitted: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
    ),
    OrderAccepted: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderRejected: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "reason": pa.dictionary(pa.int16(), pa.string()),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderPendingCancel: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderCanceled: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderCancelRejected: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "reason": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderExpired: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderTriggered: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderPendingUpdate: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderModifyRejected: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "reason": pa.dictionary(pa.int16(), pa.string()),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderUpdated: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "price": pa.float64(),
            "quantity": pa.float64(),
            "trigger_price": pa.float64(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "reconciliation": pa.bool_(),
        },
    ),
    OrderFilled: pa.schema(
        {
            "trader_id": pa.dictionary(pa.int16(), pa.string()),
            "strategy_id": pa.dictionary(pa.int16(), pa.string()),
            "account_id": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "client_order_id": pa.string(),
            "venue_order_id": pa.string(),
            "trade_id": pa.string(),
            "position_id": pa.string(),
            "order_side": pa.dictionary(pa.int8(), pa.string()),
            "order_type": pa.dictionary(pa.int8(), pa.string()),
            "last_qty": pa.float64(),
            "last_px": pa.float64(),
            "currency": pa.string(),
            "commission": pa.string(),
            "liquidity_side": pa.string(),
            "event_id": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
            "info": pa.binary(),
            "reconciliation": pa.bool_(),
        },
    ),
    BinanceBar: pa.schema(
        {
            "bar_type": pa.dictionary(pa.int16(), pa.string()),
            "instrument_id": pa.dictionary(pa.int64(), pa.string()),
            "open": pa.string(),
            "high": pa.string(),
            "low": pa.string(),
            "close": pa.string(),
            "volume": pa.string(),
            "quote_volume": pa.string(),
            "count": pa.uint64(),
            "taker_buy_base_volume": pa.string(),
            "taker_buy_quote_volume": pa.string(),
            "ts_event": pa.uint64(),
            "ts_init": pa.uint64(),
        },
    ),
}
