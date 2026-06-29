"""
Agent Workbench Database

SQLite persistence for V1 agent workbench.

Stores:
- Sessions
- Messages
- Artifact references
- Approval cards

No external API calls, no trading logic, no recommendation reducer.
"""

import json
import sqlite3
from datetime import datetime

from contracts.agent_workbench import (
    AgentSession,
    AgentMessage,
    ArtifactRef,
    WorkflowKind,
    WorkflowState,
)
from contracts.approval_card import ApprovalCard


def init_agent_workbench_db(conn: sqlite3.Connection):
    """
    Initialize agent workbench database schema.

    Args:
        conn: SQLite connection
    """
    cursor = conn.cursor()

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_id TEXT PRIMARY KEY,
            workflow_kind TEXT NOT NULL,
            workflow_state TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
        )
    """)

    # Artifact refs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_artifact_refs (
            artifact_ref_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
        )
    """)

    # Approval cards table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_approval_cards (
            approval_card_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            card_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
        )
    """)

    conn.commit()


def create_session(conn: sqlite3.Connection, session: AgentSession):
    """
    Create a new session.

    Args:
        conn: SQLite connection
        session: AgentSession to create
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO agent_sessions (session_id, workflow_kind, workflow_state, title, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session.session_id,
            session.workflow_kind.value,
            session.workflow_state.value,
            session.title,
            session.created_at.isoformat(),
            session.updated_at.isoformat(),
        ),
    )

    conn.commit()


def get_session(conn: sqlite3.Connection, session_id: str) -> AgentSession:
    """
    Get session by ID.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        AgentSession
    """
    cursor = conn.cursor()

    cursor.execute(
        "SELECT session_id, workflow_kind, workflow_state, title, created_at, updated_at FROM agent_sessions WHERE session_id = ?",
        (session_id,),
    )

    row = cursor.fetchone()
    if not row:
        raise ValueError(f"Session not found: {session_id}")

    return AgentSession(
        session_id=row[0],
        workflow_kind=WorkflowKind(row[1]),
        workflow_state=WorkflowState(row[2]),
        title=row[3],
        created_at=datetime.fromisoformat(row[4]),
        updated_at=datetime.fromisoformat(row[5]),
    )


def append_message(conn: sqlite3.Connection, message: AgentMessage):
    """
    Append message to session.

    Args:
        conn: SQLite connection
        message: AgentMessage to append
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO agent_messages (message_id, session_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            message.message_id,
            message.session_id,
            message.role,
            message.content,
            message.created_at.isoformat(),
        ),
    )

    conn.commit()


def list_messages(conn: sqlite3.Connection, session_id: str) -> list[AgentMessage]:
    """
    List messages for session in insertion order.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        List of AgentMessage
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT message_id, session_id, role, content, created_at
        FROM agent_messages
        WHERE session_id = ?
        ORDER BY rowid ASC
        """,
        (session_id,),
    )

    rows = cursor.fetchall()

    return [
        AgentMessage(
            message_id=row[0],
            session_id=row[1],
            role=row[2],
            content=row[3],
            created_at=datetime.fromisoformat(row[4]),
        )
        for row in rows
    ]


def attach_artifact_ref(conn: sqlite3.Connection, artifact_ref: ArtifactRef):
    """
    Attach artifact reference to session.

    Args:
        conn: SQLite connection
        artifact_ref: ArtifactRef to attach
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO agent_artifact_refs (artifact_ref_id, session_id, artifact_id, artifact_type, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            artifact_ref.artifact_ref_id,
            artifact_ref.session_id,
            artifact_ref.artifact_id,
            artifact_ref.artifact_type,
            artifact_ref.created_at.isoformat(),
        ),
    )

    conn.commit()


def list_artifact_refs(conn: sqlite3.Connection, session_id: str) -> list[ArtifactRef]:
    """
    List artifact refs for session in insertion order.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        List of ArtifactRef
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT artifact_ref_id, session_id, artifact_id, artifact_type, created_at
        FROM agent_artifact_refs
        WHERE session_id = ?
        ORDER BY rowid ASC
        """,
        (session_id,),
    )

    rows = cursor.fetchall()

    return [
        ArtifactRef(
            artifact_ref_id=row[0],
            session_id=row[1],
            artifact_id=row[2],
            artifact_type=row[3],
            created_at=datetime.fromisoformat(row[4]),
        )
        for row in rows
    ]


def attach_approval_card(
    conn: sqlite3.Connection, session_id: str, approval_card: ApprovalCard
):
    """
    Attach approval card to session.

    Args:
        conn: SQLite connection
        session_id: Session ID
        approval_card: ApprovalCard to attach
    """
    cursor = conn.cursor()

    # Serialize approval card to JSON
    card_data = approval_card.model_dump_json()

    cursor.execute(
        """
        INSERT INTO agent_approval_cards (approval_card_id, session_id, card_data, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            approval_card.approval_card_id,
            session_id,
            card_data,
            approval_card.created_at.isoformat(),
        ),
    )

    conn.commit()


def list_approval_cards(conn: sqlite3.Connection, session_id: str) -> list[ApprovalCard]:
    """
    List approval cards for session in insertion order.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        List of ApprovalCard
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT card_data
        FROM agent_approval_cards
        WHERE session_id = ?
        ORDER BY rowid ASC
        """,
        (session_id,),
    )

    rows = cursor.fetchall()

    return [ApprovalCard.model_validate_json(row[0]) for row in rows]


def get_session_timeline(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    """
    Get session timeline in insertion order.

    Returns messages, artifact refs, and approval cards with type information.

    Args:
        conn: SQLite connection
        session_id: Session ID

    Returns:
        List of timeline items, each with 'type' and 'content' keys
    """
    cursor = conn.cursor()

    # Union all timeline items with rowid for ordering
    cursor.execute(
        """
        SELECT 'message' as type, message_id as id, created_at, rowid
        FROM agent_messages
        WHERE session_id = ?
        UNION ALL
        SELECT 'artifact_ref' as type, artifact_ref_id as id, created_at, rowid
        FROM agent_artifact_refs
        WHERE session_id = ?
        UNION ALL
        SELECT 'approval_card' as type, approval_card_id as id, created_at, rowid
        FROM agent_approval_cards
        WHERE session_id = ?
        ORDER BY rowid ASC
        """,
        (session_id, session_id, session_id),
    )

    rows = cursor.fetchall()

    timeline = []

    for row in rows:
        item_type = row[0]
        item_id = row[1]

        if item_type == "message":
            # Fetch full message
            cursor.execute(
                "SELECT message_id, session_id, role, content, created_at FROM agent_messages WHERE message_id = ?",
                (item_id,),
            )
            msg_row = cursor.fetchone()
            message = AgentMessage(
                message_id=msg_row[0],
                session_id=msg_row[1],
                role=msg_row[2],
                content=msg_row[3],
                created_at=datetime.fromisoformat(msg_row[4]),
            )
            timeline.append({"type": "message", "content": message.model_dump()})

        elif item_type == "artifact_ref":
            # Fetch full artifact ref
            cursor.execute(
                "SELECT artifact_ref_id, session_id, artifact_id, artifact_type, created_at FROM agent_artifact_refs WHERE artifact_ref_id = ?",
                (item_id,),
            )
            ref_row = cursor.fetchone()
            artifact_ref = ArtifactRef(
                artifact_ref_id=ref_row[0],
                session_id=ref_row[1],
                artifact_id=ref_row[2],
                artifact_type=ref_row[3],
                created_at=datetime.fromisoformat(ref_row[4]),
            )
            timeline.append({"type": "artifact_ref", "content": artifact_ref.model_dump()})

        elif item_type == "approval_card":
            # Fetch full approval card
            cursor.execute(
                "SELECT card_data FROM agent_approval_cards WHERE approval_card_id = ?",
                (item_id,),
            )
            card_row = cursor.fetchone()
            approval_card = ApprovalCard.model_validate_json(card_row[0])
            timeline.append({"type": "approval_card", "content": approval_card.model_dump()})

    return timeline
