# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2020 Nautech Systems Pty Ltd. All rights reserved.
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

import unittest

from nautilus_trader.common.uuid import UUIDFactory
from nautilus_trader.core.uuid import UUID


class UUIDFactoryTests(unittest.TestCase):

    def test_factory_returns_unique_uuids(self):
        # Arrange
        factory = UUIDFactory()

        # Act
        result1 = factory.generate()
        result2 = factory.generate()
        result3 = factory.generate()

        self.assertEqual(UUID, type(result1))
        self.assertNotEqual(result1, result2)
        self.assertNotEqual(result2, result3)
