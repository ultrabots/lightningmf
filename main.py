#!/usr/bin/python
from PySide import QtGui  
from PySide import QtCore
from PySide import QtUiTools
import sys  
import os
import tempfile
import subprocess
import sqlalchemy
import os.path
import os
import sqlalchemy.orm
import sqlalchemy.ext.declarative 
from sqlalchemy import Column, Integer, String, Sequence, Boolean
from sqlalchemy.orm import relationship
import threading

db_directory = os.path.expanduser("~/.lightningmf")
if not os.path.exists(db_directory):
    os.makedirs(db_directory)
cstring = "sqlite:///" + os.path.join(db_directory, "db.sqlite")
engine = sqlalchemy.create_engine(cstring, echo=False)

# Some helpers to help use SqlAlchemy
class Base(object):
    @sqlalchemy.ext.declarative.declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    @sqlalchemy.ext.declarative.declared_attr
    def id(cls):
        return Column(Integer, Sequence(cls.__name__.lower() + "_id_seq"), primary_key=True)

Base = sqlalchemy.ext.declarative.declarative_base(cls=Base)

def Many2One(class_name, **kwargs):
    return Column(Integer, sqlalchemy.ForeignKey(class_name.lower() + ".id"), **kwargs)

# models

class Game(Base):
    name = Column(String(50), nullable=False)
    description = Column(String(200), nullable=False)
    year = Column(String(10), nullable=False)
    manufacturer = Column(String(70), nullable=False)
    status = Column(String(50), nullable=False)
    cloneof = Column(String(50))

# session

class ThreadSession:
    def __init__(self, session_class):
        self._session_class = sqlalchemy.orm.scoped_session(session_class)
    def __getattr__(self, name):
        return getattr(self._session_class(), name)
    def ensure_inited(self):
        return self._session_class()
    def remove(self):
        try:
            self._session_class.remove()
        except:
            pass

session = ThreadSession(sqlalchemy.orm.sessionmaker(bind=engine))

_local_test = threading.local()

def transactionnal(fct):
    def wrapping(*args, **kwargs):
        if getattr(_local_test, "test", 0) != 0:
            raise Exception("Multiple usages of @transactionnal")
        _local_test.test = 1
        session.ensure_inited()
        try:
            val = fct(*args, **kwargs)
            session.commit()
            return val
        finally:
            _local_test.test = 0
            session.remove()
    return wrapping

# database initialisation

def init_db():
    if len(Base.metadata.tables.keys()) == 0:
        return
    tname = Base.metadata.tables.keys()[0]
    if not engine.dialect.has_table(engine, tname):
        Base.metadata.create_all(engine) 
        @transactionnal
        def create_data():
            pass
        create_data()

def drop_db():
    Base.metadata.drop_all(engine)

# gui
class FrontendApplication:
    def launch(self):
        self.app = QtGui.QApplication(sys.argv)  

        self.loader = QtUiTools.QUiLoader()
        file = QtCore.QFile("view.ui")
        file.open(QtCore.QFile.ReadOnly)
        self.win = self.loader.load(file)
        file.close()

        self.win.move(QtGui.QDesktopWidget().availableGeometry().center() - self.win.geometry().center());
        self.settings = QtCore.QSettings("qsdoiuhvap", "xpoihybao");
        self.win.restoreGeometry(self.settings.value("geometry"));
        self.win.show()
        
        self.model = MyModel()
        self.win.itemsView.setModel(self.model)
        self.win.itemsView.horizontalHeader().setResizeMode(0, QtGui.QHeaderView.Stretch)

        self.win.actionRoms.triggered.connect(self.loadRoms)

        self.win.searchInput.textEdited.connect(self.searchChanged)

        self.app.exec_()
        
        self.settings.setValue("geometry", self.win.saveGeometry())
    
    def loadRoms(*args):
        filename = tempfile.mktemp()
        with open(filename, "w") as tmpfile:
            subprocess.check_call(["mame", "-listxml"], stdout=tmpfile)
        @transactionnal
        def parse_elements():
            import xml.etree.ElementTree as etree
            with open(filename) as tmpfile:
                doc = etree.iterparse(tmpfile)
                for event, elem in doc:
                    if elem.tag == "game":
                        name = elem.get("name")
                        desc = elem.findtext("description") or ""
                        year = elem.findtext("year") or ""
                        manu = elem.findtext("manufacturer") or ""
                        game = Game(name=name, description=desc, year=year, manufacturer=manu, status="")
                        session.add(game)

        parse_elements()

    def searchChanged(self, text):
        print "searching", text
        self.model.searchString = text
        self.model.modelReset.emit()

class MyModel(QtCore.QAbstractTableModel):
    headers = {
        0: ("Title", "description"),
        1: ("Name", "name"),
        2: ("Year", "year"),
        3: ("Manufacturer", "manufacturer"),
        4: ("Status", "status"),
        5: ("Clone of", "cloneof"),
    }
    items_per_page = 50
    max_pages = 5
    def __init__(self):
        super(MyModel, self).__init__()
        self.cache = {}
        self.count = None
        self.searchString = ""
        def reset():
            self.cache = {}
            self.count = None
        self.modelReset.connect(reset)
    @transactionnal
    def rowCount(self, *args):
        if self.count is None:
            print "query count"
            self.count = self._buildQuery().count()
        return self.count
    def _buildQuery(self):
        return session.query(Game).order_by(Game.description).filter( \
                sqlalchemy.or_(Game.description.like("%" + self.searchString + "%"), \
                Game.name.like("%" + self.searchString + "%")))
    def columnCount(self, *args):
        return len(MyModel.headers)
    @transactionnal
    def data(self, index, role):
        if role != QtCore.Qt.DisplayRole:
            return
        row = index.row()
        page = row / MyModel.items_per_page
        if not page in self.cache:
            if len(self.cache) >= MyModel.max_pages:
                del self.cache[self.cache.keys()[0]]
            print "query page", page
            result = session.execute(self._buildQuery() \
                    .offset(page * MyModel.items_per_page).limit(MyModel.items_per_page))
            dicts = [dict(x) for x in result]
            self.cache[page] = dicts
        game = self.cache[page][row % MyModel.items_per_page]
        col = MyModel.headers[index.column()][1]
        return game.get("game_" + col, "")
    def headerData(self, section, orientation, role):
        if role != QtCore.Qt.DisplayRole:
            return
        if orientation == QtCore.Qt.Horizontal:
            return MyModel.headers[section][0]

if __name__ == '__main__':  
    if len(sys.argv) >= 2 and sys.argv[1] == "-flush":
        print "flushing"
        drop_db()
    init_db()
    FrontendApplication().launch()

