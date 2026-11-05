"""Local-only command for creating the first Game Master account."""

from __future__ import annotations

import asyncio
from getpass import getpass

from loremaster.config import settings
from loremaster.models.auth import CreateUserRequest, Role
from loremaster.models.auth_repository import active_gm_count, create_user
from loremaster.models.db import Database


async def bootstrap_gm(*, username: str, password: str) -> None:
    validated = CreateUserRequest(username=username, password=password, role=Role.GM)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_url)
    try:
        await db.create_all()
        async with db.session() as sess:
            if await active_gm_count(sess):
                raise RuntimeError("an active gm account already exists")
            await create_user(
                sess,
                username=validated.username,
                password=validated.password,
                role=Role.GM,
            )
    finally:
        await db.close()


def main() -> None:
    print("Loremaster — bootstrap da conta do Mestre")
    username = input("Usuário: ").strip()
    password = getpass("Senha (mínimo 10 caracteres): ")
    confirmation = getpass("Confirme a senha: ")
    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")
    try:
        asyncio.run(bootstrap_gm(username=username, password=password))
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Conta do Mestre criada para {username!r}.")


if __name__ == "__main__":
    main()
