from utils import env
from tools.tool import tool
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime,timezone
import os

#虽然webui fastapi 把该实现的documents CURD api 已经都实现了一遍,但为了解耦防止意外,还是再写一遍

MAX_DOCUMENT_TITLE_CHARS = 200
MAX_DOCUMENT_CONTENT_CHARS = 1_000_000
MAX_DOCUMENT_BODY_BYTES = 1024 * 1024

MONGO_HOST = env("MONGO_HOST", "mongodb")
MONGO_PORT = int(env("MONGO_PORT", "27017"))
MONGO_DATABASE = env("MONGO_DATABASE", "agent")
MONGO_DOCUMENT_COLLECTION = env("MONGO_DOCUMENT_COLLECTION", "documents")

mongo_kwargs = {
    "host": MONGO_HOST,
    "port": MONGO_PORT,
    "serverSelectionTimeoutMS": 5000,
    "tz_aware": True,
}

if os.getenv("MONGO_USER"):
    mongo_kwargs.update(
        username=os.environ["MONGO_USER"],
        password=os.getenv("MONGO_PASS", ""),
        authSource="admin",
    )
mongo_client = MongoClient(**mongo_kwargs)
documents_collection = mongo_client[MONGO_DATABASE][MONGO_DOCUMENT_COLLECTION]


@tool(
    "通过文档title查询文档",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "文档title"},
        },
        "required": ["title"]
    }
)
def query_document_by_name(title):
    res=''
    for i in list(documents_collection.find({"title":title})):
        res+=f"{i['title']} <{str(i['_id'])}>\n"
        res+=f"content: {i['content']}\n"
        res+=f"created_at: {i['created_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
        res+=f"updated_at: {i['updated_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
    return res

@tool(
    "通过文档id查询文档",
    {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档ID"},
        },
        "required": ["doc_id"]
    }
)
def query_document_by_id(doc_id):
    res=''
    i=documents_collection.find_one({"_id":ObjectId(doc_id)})
    d=""
    d+=f"<title>{i['title']}</title>\n"
    d+=f"<content>{i['content']}</content>\n"
    d+=f"- created_at: {i['created_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
    d+=f"- updated_at: {i['updated_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
    res+=f"<document id={i['_id']}>{d}</document>\n"
    return res

def document_wrapper(doc_id):
    i=documents_collection.find_one({"_id":ObjectId(doc_id)})
    d=""
    d+=f"<title>{i['title']}</title>\n"
    d+=f"<content>{i['content']}</content>\n"
    d+=f"- created_at: {i['created_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
    d+=f"- updated_at: {i['updated_at'].astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
    res=f"<document id={i['_id']}>{d}</document>\n"
    return res

@tool(
    "追加内容到文档",
    {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档ID"},
            "append_content": {"type": "string", "description": "追加内容"},
            "return_final": {"type": "boolean", "description": "返回最终内容"},
        },
        "required": ["doc_id","append_content"]
    }
)
def append_to_document(doc_id,append_content,return_final=False):
    now = datetime.now(timezone.utc)
    doc = documents_collection.find_one({"_id":ObjectId(doc_id)})
    if doc is None:
        raise ValueError(f"文档不存在: {doc_id}")
    content=doc['content']+append_content
    res=''
    if len(content)>MAX_DOCUMENT_CONTENT_CHARS:
        raise ValueError(f"文档内容过长,最大允许{MAX_DOCUMENT_CONTENT_CHARS}字符")
    else:
        res = documents_collection.find_one_and_update({"_id":ObjectId(doc_id)},{"$set":{"content":content,"updated_at":now}},return_document=return_final)
    if return_final and res:
        res = document_wrapper(doc_id)
    return str(res)


@tool(
    "重写文档",
    {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档ID"},
            "content": {"type": "string", "description": "文档内容"},
            "return_final": {"type": "boolean", "description": "返回最终内容"},
        },
        "required": ["doc_id","content"]
    }
)
def rewrite_document(doc_id,content,return_final=False):
    now = datetime.now(timezone.utc)
    doc = documents_collection.find_one({"_id":ObjectId(doc_id)})
    if doc is None:
        raise ValueError(f"文档不存在: {doc_id}")
    res=''
    if len(content)>MAX_DOCUMENT_CONTENT_CHARS:
        raise ValueError(f"文档内容过长,最大允许{MAX_DOCUMENT_CONTENT_CHARS}字符")
    res = documents_collection.find_one_and_update({"_id":ObjectId(doc_id)},{"$set":{"content":content,"updated_at":now}},return_document=return_final)
    if return_final and res:
        res = document_wrapper(doc_id)
    return str(res)

@tool(
    "新建文档",
    {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "文档标题,默认为'未命名文档'"},
            "content": {"type": "string", "description": "文档内容,默认为空"},
        },
        "required": []
    }
)
def create_document(title='未命名文档',content=''):
    now = datetime.now(timezone.utc)
    if len(content)>MAX_DOCUMENT_CONTENT_CHARS:
        raise ValueError(f"文档内容过长,最大允许{MAX_DOCUMENT_CONTENT_CHARS}字符")
    res=documents_collection.insert_one({"title":title,"content":content,"pinned":False,"updated_at":now,"created_at":now})
    doc_id=res.inserted_id
    return f"{doc_id} created"


def list_documents():
    res=''
    docs_list=list(documents_collection.find())  
    if not docs_list:
        res="没有文档存在" 
    return docs_list

def system_documents_prompt():
    prompt="index_of_documents:"
    pinned=''
    for i in list_documents():
        prompt+=f"  - {i['title']} <id:{str(i['_id'])}>\n "     
        if i.get("pinned"):
            pinned+=f"{document_wrapper(str(i['_id']))}\n"
    return prompt+pinned

@tool(
    "重命名文档",
    {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档ID"},
            "title": {"type": "string", "description": "文档title"},
        },
        "required": ["doc_id","title"]
    }
)
def rename_document(doc_id,title):
    now = datetime.now(timezone.utc)
    doc = documents_collection.find_one({"_id":ObjectId(doc_id)})
    if doc is None:
        raise ValueError(f"文档不存在: {doc_id}")
    res = documents_collection.find_one_and_update({"_id":ObjectId(doc_id)},{"$set":{"title":title,"updated_at":now}})
    return f"{res['title']} : {str(res['_id'])}"