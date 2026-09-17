"""Chamada MCP local em memória com SDK oficial e banco temporário."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mcp import Client
from database import database
from mcp_server.server import criar_servidor


async def testar():
    with TemporaryDirectory(prefix="creditai-mcp-") as pasta:
        with patch.object(database, "CAMINHO_BANCO", Path(pasta) / "teste.db"):
            async with Client(criar_servidor(), raise_exceptions=True) as cliente:
                ferramentas = await cliente.list_tools()
                resultado = await cliente.call_tool("simular_credito", {"valor": 5000, "parcelas": 12, "taxa_juros_mensal": 2})
                assert not resultado.is_error
                assert resultado.structured_content["valor_parcela"] == 472.8
                assert resultado.structured_content["valor_total"] == 5673.58
                assert resultado.structured_content["total_juros"] == 673.58
                print(json.dumps({"tools": [t.name for t in ferramentas.tools],
                                  "resultado": resultado.structured_content}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    asyncio.run(testar())
