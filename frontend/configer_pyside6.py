import json
import sys
import datetime
from dataclasses import dataclass
from typing import Any, Dict, Optional
import os
import requests
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
    QFileDialog,
    QSpinBox,
)
from pathlib import Path
os.chdir(os.path.dirname(os.path.abspath(__file__)))
API_BASE = "http://127.0.0.1:13900"
TIME_DISPLAY = "yyyy-MM-dd HH:mm:ss"

PUBLIC_PROVIDER_KEYS = [
    "GUI_OPERATOR_LLM_MODEL",
    "GUI_OPERATOR_LLM_BASE",
    "SECURITY_VERIFIER_API_ENDPOINT",
    "SECURITY_VERIFIER_LLM_MODEL",
    "SECURITY_SYS_ENABLED",
    "RAG_ENABLED",
    "MC_OPERATOR_URL",
    "MC_EVENT_TRIGGER_ENABLED",
]
PRIVATE_PROVIDER_KEYS = [
    "DEEPSEEK_API_KEY",
    "SEARCH_API_KEY",
    "GUI_OPERATOR_LLM_KEY",
    "SECURITY_VERIFIER_LLM_KEY",
    "RAG_OPENAI_API_KEY",
]
LIVE2D_KEYS = [
    "LIVE2D_MODEL_PATH",
    "LIVE2D_MODEL_SCALE",
    "LIVE2D_MODEL_X",
    "LIVE2D_MODEL_Y",
    "FRONTEND_CLICK_THROUGH",
    "FRONTEND_DEFAULT_TTS_LANG",
]
AGENT_FILES = ["AGENT.md", "ROLE.md", "COREMEMORY.md", "TASK.md"]


@dataclass
class FieldWidget:
    key: str
    widget: QWidget
    value_type: str


class ApiError(Exception):
    pass


class RagDetailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RAG 详情")
        self.resize(860, 620)

        root = QVBoxLayout(self)
        self.meta_view = QPlainTextEdit()
        self.meta_view.setReadOnly(True)
        self.content_edit = QPlainTextEdit()

        root.addWidget(QLabel("元信息"))
        root.addWidget(self.meta_view, 2)
        root.addWidget(QLabel("正文"))
        root.addWidget(self.content_edit, 3)

        btn_row = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.delete_btn = QPushButton("删除")
        self.save_btn = QPushButton("保存")
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)


class TriggerDetailDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Trigger 详情")
        self.resize(680, 560)

        root = QVBoxLayout(self)

        common_group = QGroupBox("通用配置")
        common_form = QFormLayout(common_group)
        self.trigger_id_input = QLineEdit()
        self.trigger_type_combo = QComboBox()
        self.trigger_type_combo.addItems(["interval", "datetime", "py-eval"])
        self.trigger_lifespan_input = QLineEdit()
        self.trigger_lifespan_input.setPlaceholderText("可选，秒")
        self.trigger_recall_input = QPlainTextEdit()
        self.trigger_recall_input.setFixedHeight(90)
        common_form.addRow("ID", self.trigger_id_input)
        common_form.addRow("类型", self.trigger_type_combo)
        common_form.addRow("lifespan", self.trigger_lifespan_input)
        common_form.addRow("recall_description", self.trigger_recall_input)
        root.addWidget(common_group)

        self.trigger_interval_group = QGroupBox("Interval 配置")
        interval_form = QFormLayout(self.trigger_interval_group)
        self.trigger_interval_seconds = QSpinBox()
        self.trigger_interval_seconds.setRange(1, 10**9)
        self.trigger_interval_seconds.setValue(60)
        interval_form.addRow("interval_seconds", self.trigger_interval_seconds)
        root.addWidget(self.trigger_interval_group)

        self.trigger_datetime_group = QGroupBox("Datetime 配置")
        datetime_form = QFormLayout(self.trigger_datetime_group)
        self.trigger_datetime_target = QDateTimeEdit()
        self.trigger_datetime_target.setDisplayFormat(TIME_DISPLAY)
        self.trigger_datetime_target.setCalendarPopup(True)
        self.trigger_datetime_target.setDateTime(QDateTime.currentDateTime())
        datetime_form.addRow("target", self.trigger_datetime_target)
        root.addWidget(self.trigger_datetime_group)

        self.trigger_pyeval_group = QGroupBox("Py-eval 配置")
        pyeval_form = QFormLayout(self.trigger_pyeval_group)
        self.trigger_eval_code = QPlainTextEdit()
        self.trigger_eval_code.setPlaceholderText("例如: datetime.datetime.now().hour == 9")
        self.trigger_eval_code.setFixedHeight(120)
        pyeval_form.addRow("eval_code", self.trigger_eval_code)
        root.addWidget(self.trigger_pyeval_group)

        btn_row = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.save_btn = QPushButton("保存 Trigger")
        btn_row.addStretch(1)
        btn_row.addWidget(self.close_btn)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)


class ConfigerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FaustBot Configer")
        self.resize(1300, 900)

        self.state: Dict[str, Any] = {
            "config": {},
            "runtime": {},
            "agent_detail": None,
            "selected_agent": None,
            "services": [],
            "selected_service": None,
            "rag": {
                "page": 1,
                "page_size": 10,
                "total": 0,
                "total_pages": 1,
                "search": "",
                "time_from": "",
                "time_to": "",
                "items": [],
                "detail": None,
            },
            "plugins": {
                "items": [],
                "selected_id": None,
                "hot_reload": {},
            },
            "triggers": {
                "items": [],
                "selected_id": None,
            },
            "skills": {
                "items": [],
                "selected_slug": None,
                "selected_agent": None,
            },
        }

        self.public_fields: Dict[str, FieldWidget] = {}
        self.private_fields: Dict[str, FieldWidget] = {}
        self.live2d_fields: Dict[str, FieldWidget] = {}
        self.agent_file_edits: Dict[str, QPlainTextEdit] = {}
        self.plugin_config_fields: Dict[str, FieldWidget] = {}

        self._build_ui()
        self.refresh_all()

    # ---------- API ----------
    def api_request(self, method: str, path: str, payload: Optional[dict] = None, params: Optional[dict] = None):
        url = f"{API_BASE}{path}"
        try:
            resp = requests.request(method=method, url=url, json=payload, params=params, timeout=30)
        except requests.RequestException as e:
            raise ApiError(f"网络请求失败: {e}") from e

        try:
            data = resp.json()
        except Exception:
            data = {}

        if not resp.ok:
            detail = data.get("detail") if isinstance(data, dict) else None
            raise ApiError(detail or f"HTTP {resp.status_code}")

        if isinstance(data, dict) and data.get("error"):
            raise ApiError(str(data.get("error")))

        return data

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)

        top = QHBoxLayout()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_all)
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.save_btn)
        top.addStretch(1)
        main.addLayout(top)

        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)

        self._build_overview_tab()
        self._build_provider_tab()
        self._build_agent_tab()
        self._build_live2d_tab()
        self._build_rag_tab()
        self._build_runtime_tab()
        self._build_trigger_tab()
        self._build_skills_tab()
        self._build_plugins_tab()

        status = QStatusBar()
        self.setStatusBar(status)

    def _build_overview_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        cards = QHBoxLayout()
        self.current_agent_label = QLabel("当前 Agent: -")
        self.current_model_label = QLabel("默认模型: -")
        cards.addWidget(self.current_agent_label)
        cards.addWidget(self.current_model_label)
        cards.addStretch(1)
        layout.addLayout(cards)

        self.runtime_summary_view = QPlainTextEdit()
        self.runtime_summary_view.setReadOnly(True)
        layout.addWidget(self.runtime_summary_view, 1)

        self.tabs.addTab(tab, "概览")

    def _build_provider_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        self.public_box = QGroupBox("公开配置")
        self.public_form = QFormLayout(self.public_box)

        self.private_box = QGroupBox("API Keys")
        self.private_form = QFormLayout(self.private_box)

        layout.addWidget(self.public_box, 1)
        layout.addWidget(self.private_box, 1)
        self.tabs.addTab(tab, "AI Provider")

    def _build_live2d_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        group = QGroupBox("Live2D 配置")
        self.live2d_form = QFormLayout(group)
        layout.addWidget(group)

        self.model_list = QListWidget()
        layout.addWidget(QLabel("可用模型"))
        layout.addWidget(self.model_list, 1)

        self.model_list.itemDoubleClicked.connect(self._apply_selected_model_path)
        self.tabs.addTab(tab, "Live2D")

    def _build_agent_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()
        self.agent_list = QListWidget()
        self.agent_list.itemSelectionChanged.connect(self._on_agent_selected)
        left.addWidget(self.agent_list, 1)

        left_btn = QHBoxLayout()
        self.agent_create_btn = QPushButton("新建")
        self.agent_delete_btn = QPushButton("删除")
        self.agent_switch_btn = QPushButton("切换为当前")
        left_btn.addWidget(self.agent_create_btn)
        left_btn.addWidget(self.agent_delete_btn)
        left_btn.addWidget(self.agent_switch_btn)
        left.addLayout(left_btn)

        self.agent_create_btn.clicked.connect(self.create_agent)
        self.agent_delete_btn.clicked.connect(self.delete_agent)
        self.agent_switch_btn.clicked.connect(self.switch_agent)

        right = QVBoxLayout()
        self.agent_editor_tabs = QTabWidget()
        for name in AGENT_FILES:
            editor = QPlainTextEdit()
            self.agent_file_edits[name] = editor
            self.agent_editor_tabs.addTab(editor, name)
        right.addWidget(self.agent_editor_tabs, 1)

        self.agent_save_btn = QPushButton("保存 Agent 文件")
        self.agent_save_btn.clicked.connect(self.save_agent_files)
        self.open_in_default_btn = QPushButton("在默认编辑器中打开")
        self.open_in_default_btn.clicked.connect(self.open_agent_in_default_editor)
        self.del_agent_checkpoint_btn = QPushButton("删除 Agent Checkpoint(对话上下文重置)")
        self.del_agent_checkpoint_btn.clicked.connect(self.del_agent_checkpoint)
        right.addWidget(self.agent_save_btn)
        right.addWidget(self.open_in_default_btn)
        right.addWidget(self.del_agent_checkpoint_btn)

        split = QSplitter(Qt.Horizontal)
        left_holder = QWidget()
        left_holder.setLayout(left)
        right_holder = QWidget()
        right_holder.setLayout(right)
        split.addWidget(left_holder)
        split.addWidget(right_holder)
        split.setSizes([300, 900])

        layout.addWidget(split, 1)
        self.tabs.addTab(tab, "Agent 管理")

    def _build_runtime_tab(self):
        tab = QWidget()
        layout = QGridLayout(tab)

        self.reload_agent_btn = QPushButton("重建 Agent Runtime")
        self.reload_all_btn = QPushButton("重载配置并重建 Runtime")
        self.reload_agent_btn.clicked.connect(self.reload_agent_runtime)
        self.reload_all_btn.clicked.connect(self.reload_all_runtime)
        layout.addWidget(self.reload_agent_btn, 0, 0)
        layout.addWidget(self.reload_all_btn, 0, 1)

        self.service_list = QListWidget()
        self.service_list.itemSelectionChanged.connect(self._on_service_selected)
        layout.addWidget(QLabel("服务列表"), 1, 0)
        layout.addWidget(self.service_list, 2, 0)

        srv_btn = QHBoxLayout()
        self.service_start_btn = QPushButton("启动")
        self.service_stop_btn = QPushButton("停止")
        self.service_restart_btn = QPushButton("重启")
        self.service_start_btn.clicked.connect(lambda: self.service_action("start"))
        self.service_stop_btn.clicked.connect(lambda: self.service_action("stop"))
        self.service_restart_btn.clicked.connect(lambda: self.service_action("restart"))
        srv_btn.addWidget(self.service_start_btn)
        srv_btn.addWidget(self.service_stop_btn)
        srv_btn.addWidget(self.service_restart_btn)
        srv_wrap = QWidget()
        srv_wrap.setLayout(srv_btn)
        layout.addWidget(srv_wrap, 3, 0)

        self.service_log = QPlainTextEdit()
        self.service_log.setReadOnly(True)
        layout.addWidget(QLabel("服务日志"), 1, 1)
        layout.addWidget(self.service_log, 2, 1, 2, 1)

        self.tabs.addTab(tab, "运行控制")

    def _build_plugins_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()
        self.plugin_list = QListWidget()
        self.plugin_list.itemSelectionChanged.connect(self._on_plugin_selected)
        left.addWidget(QLabel("插件列表"))
        left.addWidget(self.plugin_list, 1)

        top_btn = QHBoxLayout()
        self.plugin_refresh_btn = QPushButton("刷新")
        self.plugin_reload_btn = QPushButton("重载插件")
        self.plugin_enable_btn = QPushButton("启用插件")
        self.plugin_disable_btn = QPushButton("禁用插件")
        self.plugin_delete_btn = QPushButton("删除插件")
        top_btn.addWidget(self.plugin_refresh_btn)
        top_btn.addWidget(self.plugin_reload_btn)
        top_btn.addWidget(self.plugin_enable_btn)
        top_btn.addWidget(self.plugin_disable_btn)
        top_btn.addWidget(self.plugin_delete_btn)
        left.addLayout(top_btn)

        zip_btn = QHBoxLayout()
        self.plugin_install_zip_btn = QPushButton("从 ZIP 安装")
        self.plugin_package_zip_btn = QPushButton("打包为 ZIP")
        zip_btn.addWidget(self.plugin_install_zip_btn)
        zip_btn.addWidget(self.plugin_package_zip_btn)
        left.addLayout(zip_btn)

        self.plugin_reload_mode_label = QLabel("插件重载模式: 手动")
        left.addWidget(self.plugin_reload_mode_label)

        self.plugin_refresh_btn.clicked.connect(self.load_plugins)
        self.plugin_reload_btn.clicked.connect(self.reload_plugins)
        self.plugin_enable_btn.clicked.connect(lambda: self.set_plugin_enabled(True))
        self.plugin_disable_btn.clicked.connect(lambda: self.set_plugin_enabled(False))
        self.plugin_delete_btn.clicked.connect(self.delete_plugin)
        self.plugin_install_zip_btn.clicked.connect(self.install_plugin_from_zip)
        self.plugin_package_zip_btn.clicked.connect(self.package_plugin_zip)

        right = QVBoxLayout()
        self.plugin_meta_view = QPlainTextEdit()
        self.plugin_meta_view.setReadOnly(True)
        right.addWidget(QLabel("插件详情"))
        right.addWidget(self.plugin_meta_view, 1)

        self.plugin_capabilities_view = QPlainTextEdit()
        self.plugin_capabilities_view.setReadOnly(True)
        right.addWidget(QLabel("插件能力"))
        right.addWidget(self.plugin_capabilities_view, 1)

        right.addWidget(QLabel("插件配置"))
        self.plugin_config_form = QFormLayout()
        cfg_holder = QWidget()
        cfg_holder.setLayout(self.plugin_config_form)
        right.addWidget(cfg_holder, 1)

        self.plugin_config_save_btn = QPushButton("保存配置并重载")
        self.plugin_config_save_btn.clicked.connect(self.save_plugin_config)
        right.addWidget(self.plugin_config_save_btn)

        split = QSplitter(Qt.Horizontal)
        left_holder = QWidget()
        left_holder.setLayout(left)
        right_holder = QWidget()
        right_holder.setLayout(right)
        split.addWidget(left_holder)
        split.addWidget(right_holder)
        split.setSizes([380, 920])

        layout.addWidget(split, 1)
        self.tabs.addTab(tab, "插件管理")

    def _build_skills_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)

        left = QVBoxLayout()

        agent_row = QHBoxLayout()
        self.skill_agent_combo = QComboBox()
        self.skill_agent_combo.currentTextChanged.connect(self.load_skills)
        agent_row.addWidget(QLabel("Agent"))
        agent_row.addWidget(self.skill_agent_combo, 1)
        left.addLayout(agent_row)

        self.skill_list = QListWidget()
        self.skill_list.itemSelectionChanged.connect(self._on_skill_selected)
        left.addWidget(QLabel("Skill 列表"))
        left.addWidget(self.skill_list, 1)

        btn_row = QHBoxLayout()
        self.skill_refresh_btn = QPushButton("刷新")
        self.skill_install_btn = QPushButton("安装")
        self.skill_install_zip_btn = QPushButton("从 ZIP 安装")
        self.skill_open_dir_btn = QPushButton("打开目录")
        self.skill_enable_btn = QPushButton("启用")
        self.skill_disable_btn = QPushButton("禁用")
        self.skill_delete_btn = QPushButton("删除")
        btn_row.addWidget(self.skill_refresh_btn)
        btn_row.addWidget(self.skill_install_btn)
        btn_row.addWidget(self.skill_install_zip_btn)
        btn_row.addWidget(self.skill_open_dir_btn)
        btn_row.addWidget(self.skill_enable_btn)
        btn_row.addWidget(self.skill_disable_btn)
        btn_row.addWidget(self.skill_delete_btn)
        left.addLayout(btn_row)

        self.skill_refresh_btn.clicked.connect(self.load_skills)
        self.skill_install_btn.clicked.connect(self.install_skill)
        self.skill_install_zip_btn.clicked.connect(self.install_skill_from_zip)
        self.skill_open_dir_btn.clicked.connect(self.open_skill_directory)
        self.skill_enable_btn.clicked.connect(lambda: self.set_skill_enabled(True))
        self.skill_disable_btn.clicked.connect(lambda: self.set_skill_enabled(False))
        self.skill_delete_btn.clicked.connect(self.delete_skill)

        right = QVBoxLayout()
        self.skill_meta_view = QPlainTextEdit()
        self.skill_meta_view.setReadOnly(True)
        right.addWidget(QLabel("Skill 详情"))
        right.addWidget(self.skill_meta_view, 2)

        self.skill_doc_view = QPlainTextEdit()
        self.skill_doc_view.setReadOnly(True)
        right.addWidget(QLabel("SKILL.md"))
        right.addWidget(self.skill_doc_view, 3)

        split = QSplitter(Qt.Horizontal)
        left_holder = QWidget()
        left_holder.setLayout(left)
        right_holder = QWidget()
        right_holder.setLayout(right)
        split.addWidget(left_holder)
        split.addWidget(right_holder)
        split.setSizes([420, 880])

        layout.addWidget(split, 1)
        self.tabs.addTab(tab, "Skill 管理")

    def _build_trigger_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.trigger_table = QTableWidget(0, 4)
        self.trigger_table.setHorizontalHeaderLabels(["id", "type", "lifespan", "描述"])
        self.trigger_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.trigger_table.setSelectionMode(QTableWidget.SingleSelection)
        self.trigger_table.itemSelectionChanged.connect(self._on_trigger_selected)
        self.trigger_table.itemDoubleClicked.connect(lambda _: self.open_trigger_detail())
        layout.addWidget(QLabel("Trigger 列表（仅显示 interval / datetime / py-eval）"))
        layout.addWidget(self.trigger_table, 1)

        left_btn = QHBoxLayout()
        self.trigger_refresh_btn = QPushButton("刷新")
        self.trigger_open_detail_btn = QPushButton("详情/编辑")
        self.trigger_new_btn = QPushButton("新建")
        self.trigger_delete_btn = QPushButton("删除")
        self.trigger_refresh_btn.clicked.connect(self.load_triggers)
        self.trigger_open_detail_btn.clicked.connect(self.open_trigger_detail)
        self.trigger_new_btn.clicked.connect(self.new_trigger)
        self.trigger_delete_btn.clicked.connect(self.delete_trigger)
        left_btn.addWidget(self.trigger_refresh_btn)
        left_btn.addWidget(self.trigger_open_detail_btn)
        left_btn.addWidget(self.trigger_new_btn)
        left_btn.addWidget(self.trigger_delete_btn)
        layout.addLayout(left_btn)
        self.tabs.addTab(tab, "Trigger 管理")

        self.trigger_detail_dialog = TriggerDetailDialog(self)
        self.trigger_id_input = self.trigger_detail_dialog.trigger_id_input
        self.trigger_type_combo = self.trigger_detail_dialog.trigger_type_combo
        self.trigger_lifespan_input = self.trigger_detail_dialog.trigger_lifespan_input
        self.trigger_recall_input = self.trigger_detail_dialog.trigger_recall_input
        self.trigger_interval_group = self.trigger_detail_dialog.trigger_interval_group
        self.trigger_interval_seconds = self.trigger_detail_dialog.trigger_interval_seconds
        self.trigger_datetime_group = self.trigger_detail_dialog.trigger_datetime_group
        self.trigger_datetime_target = self.trigger_detail_dialog.trigger_datetime_target
        self.trigger_pyeval_group = self.trigger_detail_dialog.trigger_pyeval_group
        self.trigger_eval_code = self.trigger_detail_dialog.trigger_eval_code

        self.trigger_type_combo.currentTextChanged.connect(self._on_trigger_type_changed)
        self.trigger_detail_dialog.save_btn.clicked.connect(self.save_trigger)
        self.trigger_detail_dialog.close_btn.clicked.connect(self.trigger_detail_dialog.close)
        self._on_trigger_type_changed(self.trigger_type_combo.currentText())

    def _build_rag_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filter_row = QHBoxLayout()
        self.rag_search_input = QLineEdit()
        self.rag_search_input.setPlaceholderText("关键词")
        self.rag_time_from = QDateTimeEdit()
        self.rag_time_to = QDateTimeEdit()
        self.rag_time_from.setDisplayFormat(TIME_DISPLAY)
        self.rag_time_to.setDisplayFormat(TIME_DISPLAY)
        self.rag_time_from.setSpecialValueText("不限")
        self.rag_time_to.setSpecialValueText("不限")
        self.rag_time_from.clear()
        self.rag_time_to.clear()

        self.rag_page_size = QComboBox()
        self.rag_page_size.addItems(["10", "20", "50"])

        self.rag_search_btn = QPushButton("搜索")
        self.rag_reset_btn = QPushButton("重置")
        self.rag_search_btn.clicked.connect(lambda: self.load_rag_documents(reset_page=True))
        self.rag_reset_btn.clicked.connect(self.reset_rag_filters)

        filter_row.addWidget(QLabel("搜索"))
        filter_row.addWidget(self.rag_search_input, 2)
        filter_row.addWidget(QLabel("开始"))
        filter_row.addWidget(self.rag_time_from)
        filter_row.addWidget(QLabel("结束"))
        filter_row.addWidget(self.rag_time_to)
        filter_row.addWidget(QLabel("每页"))
        filter_row.addWidget(self.rag_page_size)
        filter_row.addWidget(self.rag_search_btn)
        filter_row.addWidget(self.rag_reset_btn)
        layout.addLayout(filter_row)

        self.rag_table = QTableWidget(0, 5)
        self.rag_table.setHorizontalHeaderLabels(["doc_id", "status", "时间", "chunks", "file_path"])
        self.rag_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rag_table.setSelectionMode(QTableWidget.SingleSelection)
        self.rag_table.itemDoubleClicked.connect(lambda _: self.open_rag_detail())
        layout.addWidget(self.rag_table, 1)

        pager = QHBoxLayout()
        self.rag_page_info = QLabel("-")
        self.rag_prev_btn = QPushButton("上一页")
        self.rag_next_btn = QPushButton("下一页")
        self.rag_open_detail_btn = QPushButton("详情")
        self.rag_delete_btn = QPushButton("删除")
        self.rag_prev_btn.clicked.connect(self.rag_prev_page)
        self.rag_next_btn.clicked.connect(self.rag_next_page)
        self.rag_open_detail_btn.clicked.connect(self.open_rag_detail)
        self.rag_delete_btn.clicked.connect(self.delete_selected_rag)

        pager.addWidget(self.rag_page_info)
        pager.addStretch(1)
        pager.addWidget(self.rag_prev_btn)
        pager.addWidget(self.rag_next_btn)
        pager.addWidget(self.rag_open_detail_btn)
        pager.addWidget(self.rag_delete_btn)
        layout.addLayout(pager)

        self.tabs.addTab(tab, "RAG 记忆库")

        self.rag_detail_dialog = RagDetailDialog(self)
        self.rag_detail_dialog.close_btn.clicked.connect(self.rag_detail_dialog.close)
        self.rag_detail_dialog.save_btn.clicked.connect(self.save_rag_detail)
        self.rag_detail_dialog.delete_btn.clicked.connect(self.delete_rag_detail)

    # ---------- Helpers ----------
    def notify(self, text: str):
        self.statusBar().showMessage(text, 5000)

    def fail(self, title: str, err: Exception | str):
        msg = str(err)
        self.notify(msg)
        QMessageBox.critical(self, title, msg)

    def _clear_form_layout(self, form: QFormLayout):
        while form.count():
            item = form.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _widget_from_value(self, key: str, value: Any) -> FieldWidget:
        value_type = type(value).__name__
        if isinstance(value, bool):
            w = QComboBox()
            w.addItems(["true", "false"])
            w.setCurrentText("true" if value else "false")
            return FieldWidget(key=key, widget=w, value_type=value_type)

        if isinstance(value, str) and len(value) > 80:
            w = QPlainTextEdit(value)
            w.setFixedHeight(90)
            return FieldWidget(key=key, widget=w, value_type=value_type)

        w = QLineEdit("" if value is None else str(value))
        if any(token in key.upper() for token in ["KEY", "TOKEN", "SECRET", "PASSWORD"]):
            w.setEchoMode(QLineEdit.Password)
        return FieldWidget(key=key, widget=w, value_type=value_type)

    def _field_value(self, field: FieldWidget):
        w = field.widget
        if isinstance(w, QComboBox):
            text = w.currentText()
        elif isinstance(w, QPlainTextEdit):
            text = w.toPlainText()
        elif isinstance(w, QLineEdit):
            text = w.text()
        else:
            text = ""

        if field.value_type == "bool":
            return text == "true"
        if field.value_type == "int":
            return int(text) if text != "" else 0
        if field.value_type == "float":
            return float(text) if text != "" else 0.0
        if field.value_type == "json":
            raw = text.strip()
            if raw == "":
                return None
            return json.loads(raw)
        return text

    def _plugin_widget_from_schema(self, item: Dict[str, Any], value: Any) -> FieldWidget:
        key = str(item.get("key") or "")
        t = str(item.get("type") or "str").lower()
        if t in {"string", "text"}:
            t = "str"

        if t == "bool":
            w = QComboBox()
            w.addItems(["true", "false"])
            w.setCurrentText("true" if bool(value) else "false")
            return FieldWidget(key=key, widget=w, value_type="bool")

        if t == "json":
            txt = "" if value is None else json.dumps(value, ensure_ascii=False, indent=2)
            w = QPlainTextEdit(txt)
            w.setFixedHeight(100)
            return FieldWidget(key=key, widget=w, value_type="json")

        if t in {"int", "float"}:
            w = QLineEdit("" if value is None else str(value))
            return FieldWidget(key=key, widget=w, value_type=t)

        if t == "str" and isinstance(value, str) and len(value) > 120:
            w = QPlainTextEdit(value)
            w.setFixedHeight(100)
            return FieldWidget(key=key, widget=w, value_type="str")

        w = QLineEdit("" if value is None else str(value))
        if any(token in key.upper() for token in ["KEY", "TOKEN", "SECRET", "PASSWORD"]):
            w.setEchoMode(QLineEdit.Password)
        return FieldWidget(key=key, widget=w, value_type="str")

    # ---------- Load / Render ----------
    def load_config_view(self):
        data = self.api_request("GET", "/faust/admin/config")
        self.state["config"] = data

        public_cfg = (data or {}).get("public", {})
        private_cfg = (data or {}).get("private", {})

        self._clear_form_layout(self.public_form)
        self._clear_form_layout(self.private_form)
        self._clear_form_layout(self.live2d_form)
        self.public_fields.clear()
        self.private_fields.clear()
        self.live2d_fields.clear()

        for key in PUBLIC_PROVIDER_KEYS:
            field = self._widget_from_value(key, public_cfg.get(key))
            self.public_fields[key] = field
            self.public_form.addRow(QLabel(key), field.widget)

        for key in PRIVATE_PROVIDER_KEYS:
            field = self._widget_from_value(key, private_cfg.get(key))
            self.private_fields[key] = field
            self.private_form.addRow(QLabel(key), field.widget)

        for key in LIVE2D_KEYS:
            field = self._widget_from_value(key, public_cfg.get(key))
            self.live2d_fields[key] = field
            self.live2d_form.addRow(QLabel(key), field.widget)

    def load_runtime_summary(self):
        data = self.api_request("GET", "/faust/admin/runtime")
        runtime = data.get("runtime") or {}
        self.state["runtime"] = runtime

        self.current_agent_label.setText(f"当前 Agent: {runtime.get('current_agent', '-')}")
        model_path = (runtime.get("public_config") or {}).get("LIVE2D_MODEL_PATH", "-")
        self.current_model_label.setText(f"默认模型: {model_path}")
        self.runtime_summary_view.setPlainText(json.dumps(runtime, ensure_ascii=False, indent=2))

        self.model_list.clear()
        for model in runtime.get("available_models", []) or []:
            self.model_list.addItem(f"{model.get('label', '-')}: {model.get('path', '-')}")

        self.agent_list.clear()
        for agent in runtime.get("agents", []) or []:
            marker = "（当前）" if agent.get("is_current") else ""
            self.agent_list.addItem(f"{agent.get('name', '-')}{marker}")

        if hasattr(self, "skill_agent_combo"):
            selected = self.state["skills"].get("selected_agent")
            current_agent = runtime.get("current_agent")
            self.skill_agent_combo.blockSignals(True)
            self.skill_agent_combo.clear()
            for agent in runtime.get("agents", []) or []:
                name = str(agent.get("name") or "").strip()
                if name:
                    self.skill_agent_combo.addItem(name)
            target = selected or current_agent
            if target:
                idx = self.skill_agent_combo.findText(target)
                if idx >= 0:
                    self.skill_agent_combo.setCurrentIndex(idx)
            self.skill_agent_combo.blockSignals(False)

    def load_services(self):
        data = self.api_request("GET", "/faust/admin/services")
        self.state["services"] = data.get("items") or []
        self.service_list.clear()
        for srv in self.state["services"]:
            status = "运行中" if srv.get("is_running") else "未运行"
            self.service_list.addItem(f"{srv.get('key')} | {srv.get('name')} | {status} | 端口 {srv.get('port')}")

    def load_plugins(self):
        data = self.api_request("GET", "/faust/admin/plugins")
        items = data.get("items") or []

        self.state["plugins"]["items"] = items
        self.state["plugins"]["hot_reload"] = {"enabled": False, "manual_reload_only": True}
        self.plugin_reload_mode_label.setText("插件重载模式: 手动")

        selected_id = self.state["plugins"].get("selected_id")
        self.plugin_list.clear()
        row_to_select = -1
        for idx, plugin in enumerate(items):
            pid = str(plugin.get("id") or "")
            enabled = bool(plugin.get("enabled"))
            item = QListWidgetItem(f"[{ 'ON' if enabled else 'OFF' }] {pid}")
            item.setData(Qt.UserRole, pid)
            self.plugin_list.addItem(item)
            if selected_id and selected_id == pid:
                row_to_select = idx

        if row_to_select >= 0:
            self.plugin_list.setCurrentRow(row_to_select)
        elif self.plugin_list.count() > 0:
            self.plugin_list.setCurrentRow(0)

    def _selected_plugin_id(self) -> Optional[str]:
        item = self.plugin_list.currentItem()
        if not item:
            return None
        pid = item.data(Qt.UserRole)
        return str(pid) if pid else None

    def _selected_plugin_record(self) -> Optional[Dict[str, Any]]:
        pid = self._selected_plugin_id()
        if not pid:
            return None
        for plugin in self.state["plugins"].get("items") or []:
            if str(plugin.get("id")) == pid:
                return plugin
        return None

    def _on_plugin_selected(self):
        pid = self._selected_plugin_id()
        self.state["plugins"]["selected_id"] = pid
        plugin = self._selected_plugin_record()
        if not plugin:
            self.plugin_meta_view.setPlainText("")
            self.plugin_capabilities_view.setPlainText("")
            self._clear_form_layout(self.plugin_config_form)
            self.plugin_config_fields.clear()
            return

        meta_lines = [
            f"ID: {plugin.get('id', '-')}",
            f"名称: {plugin.get('name', '-')}",
            f"版本: {plugin.get('version', '-')}",
            f"作者: {plugin.get('author') or '-'}",
            f"主页: {plugin.get('homepage') or '-'}",
            f"状态: {'启用' if plugin.get('enabled') else '禁用'}",
            f"优先级: {plugin.get('priority', '-')}",
            f"权限: {', '.join(plugin.get('permissions') or []) or '-'}",
            f"描述: {plugin.get('description') or '-'}",
        ]
        self.plugin_meta_view.setPlainText("\n".join(meta_lines))

        trigger_control = plugin.get("trigger_control") or {}
        capability_lines = ["Tools:"]
        for tool in plugin.get("tools") or []:
            capability_lines.append(f"- {tool.get('name')} ({tool.get('description') or '无描述'})")
        if len(capability_lines) == 1:
            capability_lines.append("- 无")

        capability_lines.append("")
        capability_lines.append("Middlewares:")
        middlewares = plugin.get("middlewares") or []
        if not middlewares:
            capability_lines.append("- 无")
        for mw in middlewares:
            capability_lines.append(
                f"- {mw.get('name')} (prio={mw.get('priority')}, {mw.get('description') or '无描述'})"
            )

        capability_lines.append("")
        capability_lines.append("Trigger 控制能力:")
        capability_lines.append(
            f"- append_filter={bool(trigger_control.get('supports_append_filter'))}, "
            f"fire_filter={bool(trigger_control.get('supports_fire_filter'))}"
        )
        self.plugin_capabilities_view.setPlainText("\n".join(capability_lines))

        self._clear_form_layout(self.plugin_config_form)
        self.plugin_config_fields.clear()
        config = plugin.get("config") or {}
        schema = config.get("schema") or []
        values = config.get("values") or {}
        if not schema:
            self.plugin_config_form.addRow(QLabel("该插件未注册配置项。"))
        else:
            for item in schema:
                key = str(item.get("key") or "")
                if not key:
                    continue
                value = values.get(key, item.get("default"))
                field = self._plugin_widget_from_schema(item, value)
                self.plugin_config_fields[key] = field
                label = str(item.get("label") or key)
                desc = str(item.get("description") or "")
                label_text = f"{label} ({key})" if label != key else key
                if desc:
                    label_text += f"\n{desc}"
                self.plugin_config_form.addRow(QLabel(label_text), field.widget)

    def reload_plugins(self):
        try:
            self.api_request(
                "POST",
                "/faust/admin/plugins/reload",
                payload={"apply_runtime": True, "no_initial_chat": True},
            )
            self.load_plugins()
            self.notify("插件已重载并应用到运行时")
        except Exception as e:
            self.fail("重载插件失败", e)

    def set_plugin_enabled(self, enabled: bool):
        pid = self._selected_plugin_id()
        if not pid:
            return
        action = "enable" if enabled else "disable"
        try:
            self.api_request(
                "POST",
                f"/faust/admin/plugins/{requests.utils.quote(pid, safe='')}/{action}",
                payload={"apply_runtime": True, "no_initial_chat": True},
            )
            self.load_plugins()
            self.notify(f"插件 {pid} 已{'启用' if enabled else '禁用'}")
        except Exception as e:
            self.fail("插件开关失败", e)

    def save_plugin_config(self):
        pid = self._selected_plugin_id()
        if not pid:
            return
        if not self.plugin_config_fields:
            self.notify("当前插件没有可保存的配置项")
            return
        values: Dict[str, Any] = {}
        try:
            for key, field in self.plugin_config_fields.items():
                values[key] = self._field_value(field)
            self.api_request(
                "POST",
                f"/faust/admin/plugins/{requests.utils.quote(pid, safe='')}/config",
                payload={
                    "values": values,
                    "apply_runtime": True,
                    "reset_dialog": False,
                    "no_initial_chat": True,
                },
            )
            self.load_plugins()
            self.notify(f"插件 {pid} 配置已保存并重载")
        except Exception as e:
            self.fail("保存插件配置失败", e)

    def delete_plugin(self):
        pid = self._selected_plugin_id()
        if not pid:
            return
        if QMessageBox.question(self, "删除插件", f"确定删除插件 {pid} 吗？这将删除插件目录。") != QMessageBox.Yes:
            return
        try:
            self.api_request(
                "DELETE",
                f"/faust/admin/plugins/{requests.utils.quote(pid, safe='')}",
                params={"apply_runtime": "true", "reset_dialog": "false", "no_initial_chat": "true"},
            )
            self.state["plugins"]["selected_id"] = None
            self.load_plugins()
            self.notify(f"插件已删除: {pid}")
        except Exception as e:
            self.fail("删除插件失败", e)

    def install_plugin_from_zip(self):
        zip_path, _ = QFileDialog.getOpenFileName(self, "选择插件 ZIP", "", "ZIP Files (*.zip)")
        if not zip_path:
            return
        overwrite = QMessageBox.question(
            self,
            "覆盖已存在插件",
            "如果插件已存在，是否覆盖安装？",
        ) == QMessageBox.Yes
        try:
            self.api_request(
                "POST",
                "/faust/admin/plugins/install-zip",
                payload={
                    "zip_path": zip_path,
                    "overwrite": overwrite,
                    "apply_runtime": True,
                    "reset_dialog": False,
                    "no_initial_chat": True,
                },
            )
            self.load_plugins()
            self.notify("插件 ZIP 安装完成并已应用到运行时")
        except Exception as e:
            self.fail("从 ZIP 安装插件失败", e)

    def package_plugin_zip(self):
        pid = self._selected_plugin_id()
        if not pid:
            return

        output_dir = QFileDialog.getExistingDirectory(self, "选择 ZIP 输出目录（可取消使用默认目录）")
        zip_name, ok = QInputDialog.getText(self, "ZIP 文件名", "请输入 ZIP 文件名（可留空使用默认）")
        if not ok:
            return
        zip_name = zip_name.strip()

        payload: Dict[str, Any] = {"plugin_id": pid}
        if output_dir:
            payload["output_dir"] = output_dir
        if zip_name:
            payload["zip_name"] = zip_name

        try:
            data = self.api_request("POST", "/faust/admin/plugins/package-zip", payload=payload)
            package = data.get("package") or {}
            self.notify(f"插件已打包: {package.get('zip_path') or '-'}")
            QMessageBox.information(self, "打包完成", f"插件已打包为 ZIP:\n{package.get('zip_path') or '-'}")
        except Exception as e:
            self.fail("插件打包失败", e)

    def _current_skill_agent(self) -> Optional[str]:
        if not hasattr(self, "skill_agent_combo"):
            return None
        text = self.skill_agent_combo.currentText().strip()
        return text or None

    def load_skills(self):
        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        previous_agent = self.state["skills"].get("selected_agent")
        if previous_agent and previous_agent != agent_name:
            self.state["skills"]["selected_slug"] = None
        self.state["skills"]["selected_agent"] = agent_name
        data = self.api_request("GET", "/faust/admin/skills", params={"agent_name": agent_name})
        items = data.get("items") or []
        self.state["skills"]["items"] = items

        selected_slug = self.state["skills"].get("selected_slug")
        self.skill_list.blockSignals(True)
        self.skill_list.clear()
        row_to_select = -1
        for idx, sk in enumerate(items):
            slug = str(sk.get("slug") or "")
            enabled = bool(sk.get("enabled", True))
            ver = str(sk.get("version") or "-")
            missing = bool(sk.get("missing"))
            prefix = "MISSING" if missing else ("ON" if enabled else "OFF")
            item = QListWidgetItem(f"[{prefix}] {slug}  v{ver}")
            item.setData(Qt.UserRole, slug)
            self.skill_list.addItem(item)
            if selected_slug and selected_slug == slug:
                row_to_select = idx

        if row_to_select >= 0:
            self.skill_list.setCurrentRow(row_to_select)
        elif self.skill_list.count() > 0:
            self.skill_list.setCurrentRow(0)
            cur = self.skill_list.currentItem()
            self.state["skills"]["selected_slug"] = str(cur.data(Qt.UserRole)) if cur else None
        else:
            self.state["skills"]["selected_slug"] = None
            self.skill_meta_view.setPlainText("")
            self.skill_doc_view.setPlainText("")
        self.skill_list.blockSignals(False)
        if self.skill_list.count() > 0:
            self._on_skill_selected()

    def _selected_skill_slug(self) -> Optional[str]:
        item = self.skill_list.currentItem()
        if not item:
            return None
        slug = item.data(Qt.UserRole)
        return str(slug) if slug else None

    def _on_skill_selected(self):
        slug = self._selected_skill_slug()
        self.state["skills"]["selected_slug"] = slug
        items = self.state["skills"].get("items") or []
        by_slug = {str(it.get("slug") or ""): it for it in items}
        if not slug or slug not in by_slug:
            self.skill_meta_view.setPlainText("")
            self.skill_doc_view.setPlainText("")
            return

        selected = by_slug.get(slug) or {}
        if bool(selected.get("missing")):
            self.skill_meta_view.setPlainText(
                "\n".join(
                    [
                        f"Slug: {slug}",
                        "状态: 目录缺失（仅存在于 skills.state.json）",
                        f"Path: {selected.get('path') or '-'}",
                        "",
                        "请删除该条目或重新安装该 Skill。",
                    ]
                )
            )
            self.skill_doc_view.setPlainText("")
            return

        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        try:
            data = self.api_request(
                "GET",
                f"/faust/admin/skills/{requests.utils.quote(slug, safe='')}",
                params={"agent_name": agent_name},
            )
            detail = data.get("detail") or {}
            meta = detail.get("meta") or {}
            lines = [
                f"Slug: {detail.get('slug', slug)}",
                f"Version: {meta.get('version') or '-'}",
                f"Enabled: {bool(detail.get('enabled', True))}",
                f"Installed At: {detail.get('installed_at') or '-'}",
                f"Source: {detail.get('source') or '-'}",
                f"Path: {detail.get('path') or '-'}",
                "",
                "Meta:",
                json.dumps(meta, ensure_ascii=False, indent=2),
                "",
                "Files:",
                "\n".join(detail.get("files") or []),
            ]
            self.skill_meta_view.setPlainText("\n".join(lines))
            self.skill_doc_view.setPlainText(str(detail.get("skill_md") or ""))
        except Exception as e:
            self.skill_meta_view.setPlainText("")
            self.skill_doc_view.setPlainText("")
            self.state["skills"]["selected_slug"] = None
            if "Skill 不存在" in str(e):
                self.notify(f"Skill 不存在或已切换 Agent: {slug}")
                return
            self.fail("读取 Skill 详情失败", e)

    def install_skill(self):
        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        slug, ok = QInputDialog.getText(self, "安装 Skill", "请输入 Skill slug")
        if not ok or not slug.strip():
            return
        slug = slug.strip()
        overwrite = QMessageBox.question(
            self,
            "覆盖已存在 Skill",
            "若 Skill 已存在，是否覆盖安装？",
        ) == QMessageBox.Yes
        try:
            self.api_request(
                "POST",
                "/faust/admin/skills/install",
                payload={"slug": slug, "agent_name": agent_name, "overwrite": overwrite},
            )
            self.state["skills"]["selected_slug"] = slug
            self.load_skills()
            self.notify(f"Skill 已安装: {slug}")
        except Exception as e:
            self.fail("安装 Skill 失败", e)

    def install_skill_from_zip(self):
        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        zip_path, _ = QFileDialog.getOpenFileName(self, "选择 Skill ZIP", "", "ZIP Files (*.zip)")
        if not zip_path:
            return
        overwrite = QMessageBox.question(
            self,
            "覆盖已存在 Skill",
            "若 Skill 已存在，是否覆盖安装？",
        ) == QMessageBox.Yes
        try:
            data = self.api_request(
                "POST",
                "/faust/admin/skills/install-zip",
                payload={"zip_path": zip_path, "agent_name": agent_name, "overwrite": overwrite},
            )
            item = data.get("item") or {}
            installed_slug = str(item.get("slug") or "").strip()
            self.state["skills"]["selected_slug"] = installed_slug or None
            self.load_skills()
            self.notify(f"Skill ZIP 安装完成: {installed_slug or '-'}")
        except Exception as e:
            self.fail("从 ZIP 安装 Skill 失败", e)

    def open_skill_directory(self):
        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        slug = self._selected_skill_slug()
        if slug:
            target = Path(f"../backend/agents/{agent_name}/skill.d/{slug}").resolve()
        else:
            target = Path(f"../backend/agents/{agent_name}/skill.d").resolve()
        try:
            if not target.exists():
                QMessageBox.warning(self, "目录不存在", f"目录不存在:\n{target}")
                return
            os.startfile(target)
            self.notify(f"已打开目录: {target}")
        except Exception as e:
            self.fail("打开 Skill 目录失败", e)

    def set_skill_enabled(self, enabled: bool):
        slug = self._selected_skill_slug()
        if not slug:
            return
        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        action = "enable" if enabled else "disable"
        try:
            self.api_request(
                "POST",
                f"/faust/admin/skills/{requests.utils.quote(slug, safe='')}/{action}",
                payload={"agent_name": agent_name},
            )
            self.load_skills()
            self.notify(f"Skill {slug} 已{'启用' if enabled else '禁用'}")
        except Exception as e:
            self.fail("Skill 状态切换失败", e)

    def delete_skill(self):
        slug = self._selected_skill_slug()
        if not slug:
            return
        agent_name = self._current_skill_agent() or self.state["runtime"].get("current_agent")
        if not agent_name:
            return
        if QMessageBox.question(self, "删除 Skill", f"确定删除 Skill {slug} 吗？") != QMessageBox.Yes:
            return
        try:
            self.api_request(
                "DELETE",
                f"/faust/admin/skills/{requests.utils.quote(slug, safe='')}",
                params={"agent_name": agent_name},
            )
            self.state["skills"]["selected_slug"] = None
            self.load_skills()
            self.notify(f"Skill 已删除: {slug}")
        except Exception as e:
            self.fail("删除 Skill 失败", e)

    def load_rag_documents(self, reset_page: bool = False):
        rag = self.state["rag"]
        if reset_page:
            rag["page"] = 1

        rag["search"] = self.rag_search_input.text().strip()
        rag["page_size"] = int(self.rag_page_size.currentText())
        rag["time_from"] = self.rag_time_from.text().strip()
        rag["time_to"] = self.rag_time_to.text().strip()

        params = {
            "page": rag["page"],
            "page_size": rag["page_size"],
            "search": rag["search"] or None,
            "time_from": rag["time_from"] or None,
            "time_to": rag["time_to"] or None,
        }
        data = self.api_request("GET", "/faust/admin/rag/documents", params=params)

        rag["items"] = data.get("documents") or []
        p = data.get("pagination") or {}
        rag["page"] = int(p.get("page") or rag["page"])
        rag["page_size"] = int(p.get("page_size") or rag["page_size"])
        rag["total"] = int(p.get("total") or 0)
        rag["total_pages"] = int(p.get("total_pages") or 1)

        self.rag_table.setRowCount(len(rag["items"]))
        for i, doc in enumerate(rag["items"]):
            self.rag_table.setItem(i, 0, QTableWidgetItem(str(doc.get("doc_id", ""))))
            self.rag_table.setItem(i, 1, QTableWidgetItem(str(doc.get("status", ""))))
            self.rag_table.setItem(i, 2, QTableWidgetItem(str(doc.get("updated_at") or doc.get("created_at") or "")))
            self.rag_table.setItem(i, 3, QTableWidgetItem(str(doc.get("chunks_count", 0))))
            self.rag_table.setItem(i, 4, QTableWidgetItem(str(doc.get("file_path") or "")))

        self.rag_page_info.setText(
            f"第 {rag['page']}/{max(rag['total_pages'], 1)} 页 · 每页 {rag['page_size']} · 共 {rag['total']} 条"
        )

    def refresh_all(self):
        try:
            self.load_config_view()
            self.load_runtime_summary()
            self.load_services()
            self.load_rag_documents(reset_page=False)
            self.load_triggers()
            self.load_skills()
            self.load_plugins()
            self.notify("已刷新配置与运行状态")
        except Exception as e:
            self.fail("刷新失败", e)

    # ---------- Actions ----------
    def save_config(self):
        try:
            public_values = {k: self._field_value(v) for k, v in self.public_fields.items()}
            private_values = {k: self._field_value(v) for k, v in self.private_fields.items()}
            live2d_values = {k: self._field_value(v) for k, v in self.live2d_fields.items()}
            public_values.update(live2d_values)

            self.api_request("POST", "/faust/admin/config", payload={"public": public_values, "private": private_values})
            self.notify("配置已保存")
            self.load_config_view()
            self.load_runtime_summary()
        except Exception as e:
            self.fail("保存配置失败", e)

    def _apply_selected_model_path(self):
        row = self.model_list.currentRow()
        if row < 0:
            return
        text = self.model_list.currentItem().text()
        path = text.split(":", 1)[1].strip() if ":" in text else text
        target = self.live2d_fields.get("LIVE2D_MODEL_PATH")
        if not target:
            return
        w = target.widget
        if isinstance(w, QLineEdit):
            w.setText(path)

    def _selected_agent_name(self) -> Optional[str]:
        item = self.agent_list.currentItem()
        if not item:
            return None
        text = item.text()
        return text.replace("（当前）", "").strip()

    def _on_agent_selected(self):
        name = self._selected_agent_name()
        if not name:
            return
        self.state["selected_agent"] = name
        try:
            data = self.api_request("GET", f"/faust/admin/agents/{requests.utils.quote(name, safe='')}")
            detail = data.get("detail") or {}
            self.state["agent_detail"] = detail
            files = detail.get("files") or {}
            for f in AGENT_FILES:
                self.agent_file_edits[f].setPlainText(files.get(f, ""))
            self.notify(f"已载入 Agent: {name}")
        except Exception as e:
            self.fail("读取 Agent 失败", e)

    def create_agent(self):
        name, ok = QInputDialog.getText(self, "创建 Agent", "请输入 Agent 名称")
        if not ok or not name.strip():
            return
        name = name.strip()
        try:
            self.api_request("POST", "/faust/admin/agents", payload={"agent_name": name})
            self.load_runtime_summary()
            self.notify(f"已创建 Agent: {name}")
        except Exception as e:
            self.fail("创建 Agent 失败", e)

    def delete_agent(self):
        name = self.state.get("selected_agent")
        if not name:
            return
        if QMessageBox.question(self, "删除 Agent", f"确定删除 {name} 吗？") != QMessageBox.Yes:
            return
        try:
            self.api_request("DELETE", f"/faust/admin/agents/{requests.utils.quote(name, safe='')}")
            self.state["selected_agent"] = None
            self.state["agent_detail"] = None
            self.load_runtime_summary()
            self.notify(f"已删除 Agent: {name}")
        except Exception as e:
            self.fail("删除 Agent 失败", e)

    def switch_agent(self):
        name = self.state.get("selected_agent")
        if not name:
            return
        try:
            self.api_request("POST", "/faust/admin/agents/switch", payload={"agent_name": name})
            self.load_runtime_summary()
            self.refresh_all()
            self.notify(f"已切换 Agent: {name}")
        except Exception as e:
            self.fail("切换 Agent 失败", e)

    def save_agent_files(self):
        name = self.state.get("selected_agent")
        if not name:
            return
        files = {k: self.agent_file_edits[k].toPlainText() for k in AGENT_FILES}
        try:
            self.api_request(
                "PUT",
                f"/faust/admin/agents/{requests.utils.quote(name, safe='')}/files",
                payload={"files": files},
            )
            self.notify(f"Agent 文件已保存: {name}")
        except Exception as e:
            self.fail("保存 Agent 文件失败", e)
    def open_agent_in_default_editor(self):

        name = self.state.get("selected_agent")
        if not name:
            return
        try:
            os.startfile(Path(f"../backend/agents/{name}/AGENT.md").resolve())
            os.startfile(Path(f"../backend/agents/{name}/ROLE.md").resolve())
            os.startfile(Path(f"../backend/agents/{name}/COREMEMORY.md").resolve())
            os.startfile(Path(f"../backend/agents/{name}/TASK.md").resolve())
        except Exception as e:
            self.fail("打开 Agent 失败", e)
    def reload_agent_runtime(self):
        try:
            self.api_request("POST", "/faust/admin/runtime/reload-agent")
            self.load_runtime_summary()
            self.notify("Agent Runtime 已重建")
        except Exception as e:
            self.fail("重建 Agent Runtime 失败", e)

    def reload_all_runtime(self):
        try:
            self.api_request("POST", "/faust/admin/runtime/reload-all")
            self.load_runtime_summary()
            self.notify("运行时已重载")
        except Exception as e:
            self.fail("重载运行时失败", e)

    def _selected_service_key(self) -> Optional[str]:
        item = self.service_list.currentItem()
        if not item:
            return None
        raw = item.text().split("|", 1)[0].strip()
        return raw or None

    def _on_service_selected(self):
        key = self._selected_service_key()
        if not key:
            return
        self.state["selected_service"] = key
        try:
            data = self.api_request(
                "GET",
                f"/faust/admin/services/{requests.utils.quote(key, safe='')}",
                params={"include_log": "true"},
            )
            item = data.get("item") or {}
            self.service_log.setPlainText(item.get("log_tail") or "暂无日志")
        except Exception as e:
            self.fail("读取服务日志失败", e)

    def service_action(self, action: str):
        key = self.state.get("selected_service")
        if not key:
            return
        try:
            self.api_request("POST", f"/faust/admin/services/{requests.utils.quote(key, safe='')}/{action}")
            self.load_services()
            self.notify(f"服务 {key} 已执行 {action}")
        except Exception as e:
            self.fail("服务操作失败", e)

    # ---------- RAG ----------
    def reset_rag_filters(self):
        self.rag_search_input.clear()
        self.rag_page_size.setCurrentText("10")
        self.rag_time_from.clear()
        self.rag_time_to.clear()
        self.state["rag"]["page"] = 1
        try:
            self.load_rag_documents(reset_page=True)
        except Exception as e:
            self.fail("重置 RAG 过滤失败", e)

    def rag_prev_page(self):
        rag = self.state["rag"]
        if rag["page"] <= 1:
            return
        rag["page"] -= 1
        try:
            self.load_rag_documents(reset_page=False)
        except Exception as e:
            self.fail("分页失败", e)

    def rag_next_page(self):
        rag = self.state["rag"]
        if rag["page"] >= max(rag["total_pages"], 1):
            return
        rag["page"] += 1
        try:
            self.load_rag_documents(reset_page=False)
        except Exception as e:
            self.fail("分页失败", e)

    def _current_rag_doc_id(self) -> Optional[str]:
        row = self.rag_table.currentRow()
        if row < 0:
            return None
        item = self.rag_table.item(row, 0)
        return item.text().strip() if item else None

    def del_agent_checkpoint(self):
        name = self.state.get("selected_agent")
        if not name:
            return
        if QMessageBox.question(self, "删除 Agent Checkpoint", f"确定删除 {name} 的 Agent Checkpoint 吗？这将导致对话上下文重置。") != QMessageBox.Yes:
            return
        try:
            self.api_request("DELETE", f"/faust/admin/agents/{requests.utils.quote(name, safe='')}/checkpoint")
            self.notify(f"{name} 的 Agent Checkpoint 已删除，对话上下文已重置")
        except Exception as e:
            self.fail("删除 Agent Checkpoint 失败", e)
    def open_rag_detail(self):
        doc_id = self._current_rag_doc_id()
        if not doc_id:
            return
        try:
            encoded_doc_id = requests.utils.quote(doc_id, safe='')
            meta_data = self.api_request("GET", f"/faust/admin/rag/documents/{encoded_doc_id}")
            content_data = self.api_request("GET", f"/faust/admin/rag/documents/{encoded_doc_id}/content")

            meta = meta_data.get("document") if isinstance(meta_data, dict) else None
            if not isinstance(meta, dict):
                # 兼容旧结构
                meta = meta_data if isinstance(meta_data, dict) else {"doc_id": doc_id}

            content = ""
            if isinstance(content_data, dict):
                # backend-main 当前会包装成: {"status":"ok", "content": {"text": "..."}}
                wrapped = content_data.get("content")
                if isinstance(wrapped, dict):
                    content = str(wrapped.get("text") or "")
                else:
                    content = str(content_data.get("text") or "")

            detail = {"document": meta, "content": content}
            self.state["rag"]["detail"] = detail

            self.rag_detail_dialog.setWindowTitle(f"RAG 详情 · {meta.get('doc_id', doc_id)}")
            self.rag_detail_dialog.meta_view.setPlainText(json.dumps(meta, ensure_ascii=False, indent=2))
            self.rag_detail_dialog.content_edit.setPlainText(str(content))
            self.rag_detail_dialog.show()
            self.rag_detail_dialog.raise_()
            self.rag_detail_dialog.activateWindow()
        except Exception as e:
            self.fail("打开 RAG 详情失败", e)

    def save_rag_detail(self):
        detail = self.state["rag"].get("detail")
        if not detail:
            return
        doc = detail.get("document") or {}
        doc_id = doc.get("doc_id")
        if not doc_id:
            return
        text = self.rag_detail_dialog.content_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "正文不能为空")
            return
        try:
            self.api_request(
                "PUT",
                f"/faust/admin/rag/documents/{requests.utils.quote(str(doc_id), safe='')}",
                payload={"text": text, "file_path": doc.get("file_path")},
            )
            self.notify(f"RAG 记录已保存: {doc_id}")
            self.open_rag_detail()
            self.load_rag_documents(reset_page=False)
        except Exception as e:
            self.fail("保存 RAG 失败", e)

    def delete_selected_rag(self):
        doc_id = self._current_rag_doc_id()
        if not doc_id:
            return
        if QMessageBox.question(self, "删除 RAG", f"确定删除 {doc_id} 吗？") != QMessageBox.Yes:
            return
        self._delete_rag(doc_id, close_dialog=False)

    def delete_rag_detail(self):
        detail = self.state["rag"].get("detail") or {}
        doc = detail.get("document") or {}
        doc_id = doc.get("doc_id")
        if not doc_id:
            return
        if QMessageBox.question(self, "删除 RAG", f"确定删除 {doc_id} 吗？") != QMessageBox.Yes:
            return
        self._delete_rag(str(doc_id), close_dialog=True)

    def _delete_rag(self, doc_id: str, close_dialog: bool):
        try:
            self.api_request("DELETE", f"/faust/admin/rag/documents/{requests.utils.quote(doc_id, safe='')}")
            if close_dialog:
                self.rag_detail_dialog.close()
            self.state["rag"]["detail"] = None
            self.load_rag_documents(reset_page=False)
            self.notify(f"RAG 记录已删除: {doc_id}")
        except Exception as e:
            self.fail("删除 RAG 失败", e)

    # ---------- Trigger ----------
    def _allowed_trigger_types(self) -> set[str]:
        return {"interval", "datetime", "py-eval"}

    def _on_trigger_type_changed(self, t: str):
        self.trigger_interval_group.setVisible(t == "interval")
        self.trigger_datetime_group.setVisible(t == "datetime")
        self.trigger_pyeval_group.setVisible(t == "py-eval")

    def _selected_trigger_id(self) -> Optional[str]:
        row = self.trigger_table.currentRow()
        if row < 0:
            return None
        item = self.trigger_table.item(row, 0)
        return item.text().strip() if item else None

    def _safe_parse_qdatetime(self, raw: str) -> QDateTime:
        text = (raw or "").strip()
        if not text:
            return QDateTime.currentDateTime()

        dt_obj = QDateTime.fromString(text, TIME_DISPLAY)
        if dt_obj.isValid():
            return dt_obj
        dt_obj = QDateTime.fromString(text, Qt.ISODate)
        if dt_obj.isValid():
            return dt_obj
        dt_obj = QDateTime.fromString(text, Qt.ISODateWithMs)
        if dt_obj.isValid():
            return dt_obj

        try:
            py_dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
            return QDateTime(py_dt)
        except Exception:
            return QDateTime.currentDateTime()

    def _apply_trigger_to_form(self, item: Dict[str, Any]):
        self.trigger_id_input.setText(str(item.get("id") or ""))
        t = str(item.get("type") or "interval")
        if t not in self._allowed_trigger_types():
            t = "interval"
        self.trigger_type_combo.setCurrentText(t)

        lifespan = item.get("lifespan")
        self.trigger_lifespan_input.setText("" if lifespan in (None, "") else str(lifespan))
        self.trigger_recall_input.setPlainText(str(item.get("recall_description") or ""))

        self.trigger_interval_seconds.setValue(max(1, int(item.get("interval_seconds") or 60)))
        self.trigger_datetime_target.setDateTime(
            self._safe_parse_qdatetime(str(item.get("target") or ""))
        )
        self.trigger_eval_code.setPlainText(str(item.get("eval_code") or ""))
        self._on_trigger_type_changed(t)

    def _collect_trigger_payload(self) -> Dict[str, Any]:
        trigger_id = self.trigger_id_input.text().strip()
        if not trigger_id:
            raise ValueError("Trigger ID 不能为空")

        t = self.trigger_type_combo.currentText().strip()
        if t not in self._allowed_trigger_types():
            raise ValueError("不支持的 Trigger 类型")

        payload: Dict[str, Any] = {
            "id": trigger_id,
            "type": t,
        }

        recall = self.trigger_recall_input.toPlainText().strip()
        if recall:
            payload["recall_description"] = recall

        lifespan_text = self.trigger_lifespan_input.text().strip()
        if lifespan_text:
            lifespan = int(lifespan_text)
            if lifespan <= 0:
                raise ValueError("lifespan 必须是正整数")
            payload["lifespan"] = lifespan

        if t == "interval":
            payload["interval_seconds"] = int(self.trigger_interval_seconds.value())
        elif t == "datetime":
            payload["target"] = self.trigger_datetime_target.dateTime().toString(TIME_DISPLAY)
        elif t == "py-eval":
            code = self.trigger_eval_code.toPlainText().strip()
            if not code:
                raise ValueError("py-eval 类型必须填写 eval_code")
            payload["eval_code"] = code

        return payload

    def load_triggers(self):
        data = self.api_request("GET", "/faust/admin/triggers")
        items = data.get("items") or []
        allowed = self._allowed_trigger_types()
        filtered = [t for t in items if str((t or {}).get("type") or "") in allowed]
        self.state["triggers"]["items"] = filtered

        selected_id = self.state["triggers"].get("selected_id")
        self.trigger_table.setRowCount(len(filtered))
        row_to_select = -1
        for i, trig in enumerate(filtered):
            tid = str(trig.get("id") or "")
            ttype = str(trig.get("type") or "")
            lifespan = "" if trig.get("lifespan") is None else str(trig.get("lifespan"))
            desc = str(trig.get("recall_description") or "")
            self.trigger_table.setItem(i, 0, QTableWidgetItem(tid))
            self.trigger_table.setItem(i, 1, QTableWidgetItem(ttype))
            self.trigger_table.setItem(i, 2, QTableWidgetItem(lifespan))
            self.trigger_table.setItem(i, 3, QTableWidgetItem(desc))
            if selected_id and selected_id == tid:
                row_to_select = i

        if row_to_select >= 0:
            self.trigger_table.setCurrentCell(row_to_select, 0)
        elif self.trigger_table.rowCount() > 0:
            self.trigger_table.setCurrentCell(0, 0)
        else:
            self.new_trigger()

    def _on_trigger_selected(self):
        tid = self._selected_trigger_id()
        self.state["triggers"]["selected_id"] = tid

    def open_trigger_detail(self):
        tid = self._selected_trigger_id()
        if not tid:
            return
        item = None
        for t in self.state["triggers"].get("items") or []:
            if str(t.get("id") or "") == tid:
                item = t
                break
        if not item:
            return
        self._apply_trigger_to_form(item)
        self.trigger_detail_dialog.setWindowTitle(f"Trigger 详情 · {tid}")
        self.trigger_detail_dialog.show()
        self.trigger_detail_dialog.raise_()
        self.trigger_detail_dialog.activateWindow()

    def new_trigger(self):
        self.trigger_id_input.clear()
        self.trigger_type_combo.setCurrentText("interval")
        self.trigger_lifespan_input.clear()
        self.trigger_recall_input.clear()
        self.trigger_interval_seconds.setValue(60)
        self.trigger_datetime_target.setDateTime(QDateTime.currentDateTime())
        self.trigger_eval_code.clear()
        self.state["triggers"]["selected_id"] = None
        self.trigger_detail_dialog.setWindowTitle("新建 Trigger")
        self.trigger_detail_dialog.show()
        self.trigger_detail_dialog.raise_()
        self.trigger_detail_dialog.activateWindow()

    def save_trigger(self):
        try:
            payload = self._collect_trigger_payload()
            self.api_request("POST", "/faust/admin/triggers", payload=payload)
            self.state["triggers"]["selected_id"] = payload.get("id")
            self.load_triggers()
            self.notify(f"Trigger 已保存: {payload.get('id')}")
            self.trigger_detail_dialog.close()
        except Exception as e:
            self.fail("保存 Trigger 失败", e)

    def delete_trigger(self):
        tid = self._selected_trigger_id() or self.trigger_id_input.text().strip()
        if not tid:
            return
        if QMessageBox.question(self, "删除 Trigger", f"确定删除 {tid} 吗？") != QMessageBox.Yes:
            return
        try:
            self.api_request("DELETE", f"/faust/admin/triggers/{requests.utils.quote(tid, safe='')}")
            self.state["triggers"]["selected_id"] = None
            self.load_triggers()
            self.notify(f"Trigger 已删除: {tid}")
        except Exception as e:
            self.fail("删除 Trigger 失败", e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Faust Configer")
    window = ConfigerWindow()
    window.show()
    sys.exit(app.exec())
