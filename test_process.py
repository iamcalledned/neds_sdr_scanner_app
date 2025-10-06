import asyncio, numpy as np
from neds_sdr.core.channel import Channel
from neds_sdr.core.event_bus import EventBus
from neds_sdr.core.rtl_tcp_client import RTL_TCP_Client

async def test_channel():
    # mock receiver
    class Dummy:
        name = "TEST"
        client = RTL_TCP_Client("127.0.0.1", 1234)

    event_bus = EventBus()
    ch = Channel("ch_0", 158.9925e6, -45.0, None, None, "test_sink", Dummy(), event_bus)
    iq = np.random.randint(0, 255, 16384).astype(np.uint8).astype(np.float32)
    iq = (iq - 127.5) / 127.5
    await ch.process_samples(iq)

asyncio.run(test_channel())
