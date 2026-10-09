"""Shared, local shopping lists independent of Home Assistant."""
from contextlib import closing
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.db import connect
from app.pets import family, carer, editor, board_editor

router = APIRouter(prefix="/api/family/shopping", tags=["shopping"])


def initialize_shopping(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS shopping_lists (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    conn.execute("""CREATE TABLE IF NOT EXISTS shopping_items (
        id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL, name TEXT NOT NULL,
        quantity TEXT NOT NULL, category TEXT NOT NULL, note TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0)""")


class ListPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class ItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    quantity: str = Field(default="", max_length=60)
    category: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=320)


class ItemState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done: bool


def require_list(conn, list_id):
    if not conn.execute("SELECT id FROM shopping_lists WHERE id=?", (list_id,)).fetchone():
        raise HTTPException(404, "Listen findes ikke")


@router.get("")
def read_lists(user=Depends(family)):
    with closing(connect()) as conn:
        lists = [{**dict(row), "items": [dict(item) for item in conn.execute(
            "SELECT id,name,quantity,category,note,done FROM shopping_items WHERE list_id=? ORDER BY done,category,id", (row["id"],))]}
            for row in conn.execute("SELECT * FROM shopping_lists ORDER BY id")]
    return {"lists":lists, "can_manage":user["role"] in {"owner","adult"},
            "can_create_list":user["role"] in {"owner","adult","wall_display"},
            "can_shop":user["role"] in {"owner","adult","child","wall_display"}}


@router.post("", status_code=201)
def create_list(payload: ListPayload, user=Depends(board_editor)):
    with closing(connect()) as conn, conn:
        if conn.execute("SELECT COUNT(*) FROM shopping_lists").fetchone()[0] >= 30:
            raise HTTPException(409, "Der kan højst oprettes 30 lister")
        return {"id": conn.execute("INSERT INTO shopping_lists(name) VALUES (?)", (payload.name,)).lastrowid}


@router.put("/{list_id}")
def rename_list(list_id: int, payload: ListPayload, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_list(conn,list_id)
        conn.execute("UPDATE shopping_lists SET name=? WHERE id=?", (payload.name,list_id))
    return {"ok":True}


@router.delete("/{list_id}")
def delete_list(list_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_list(conn,list_id)
        conn.execute("DELETE FROM shopping_items WHERE list_id=?", (list_id,))
        conn.execute("DELETE FROM shopping_lists WHERE id=?", (list_id,))
    return {"ok":True}


@router.delete("/{list_id}/completed")
def clear_completed(list_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_list(conn,list_id)
        conn.execute("DELETE FROM shopping_items WHERE list_id=? AND done=1", (list_id,))
    return {"ok":True}


@router.post("/{list_id}/items", status_code=201)
def create_item(list_id: int, payload: ItemPayload, user=Depends(carer)):
    with closing(connect()) as conn, conn:
        require_list(conn,list_id)
        if conn.execute("SELECT COUNT(*) FROM shopping_items WHERE list_id=?",(list_id,)).fetchone()[0]>=500:
            raise HTTPException(409,"Listen kan højst indeholde 500 varer")
        return {"id":conn.execute("INSERT INTO shopping_items(list_id,name,quantity,category,note) VALUES (?,?,?,?,?)",
                                  (list_id,payload.name,payload.quantity,payload.category,payload.note)).lastrowid}


@router.put("/{list_id}/items/{item_id}")
def edit_item(list_id: int, item_id: int, payload: ItemPayload, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor=conn.execute("UPDATE shopping_items SET name=?,quantity=?,category=?,note=? WHERE id=? AND list_id=?",
                            (payload.name,payload.quantity,payload.category,payload.note,item_id,list_id))
        if not cursor.rowcount: raise HTTPException(404,"Varen findes ikke")
    return {"ok":True}


@router.put("/{list_id}/items/{item_id}/state")
def check_item(list_id: int, item_id: int, payload: ItemState, user=Depends(carer)):
    with closing(connect()) as conn, conn:
        cursor=conn.execute("UPDATE shopping_items SET done=? WHERE id=? AND list_id=?",(payload.done,item_id,list_id))
        if not cursor.rowcount: raise HTTPException(404,"Varen findes ikke")
    return {"ok":True}


@router.delete("/{list_id}/items/{item_id}")
def delete_item(list_id: int, item_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor=conn.execute("DELETE FROM shopping_items WHERE id=? AND list_id=?",(item_id,list_id))
        if not cursor.rowcount: raise HTTPException(404,"Varen findes ikke")
    return {"ok":True}
