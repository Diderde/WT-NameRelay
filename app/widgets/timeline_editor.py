"""Superseded canvas prototype kept only for source-history comparison.

No page instantiates this widget: the PyQtGraph timeline
(``app/widgets/pyqtgraph_timeline.py``) replaced it, see
``TIMELINE_COMPONENT_EVALUATION.md``. Its palette is hard-coded dark and
does not follow the application theme, so do not wire it into the UI
without a theme pass first.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from app.audio.models import AudioClip, format_ms


class _Mode(str,Enum): NONE='none';TRIM_LEFT='trim_left';TRIM_RIGHT='trim_right';MOVE='move'
class TimelineEditor(QWidget):
    selection_changed=Signal(set);seek_requested=Signal(int);trim_preview=Signal(str,int,int);trim_committed=Signal(str,int,int);move_committed=Signal(set,int);zoom_requested=Signal(float)
    EDGE=10
    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumHeight(210);self.setMouseTracking(True);self._items=();self._selected=set();self._position_ms=0;self._pps=10.;self._mode=_Mode.NONE;self._item=None;self._x=0;self._start=0;self._end=0
    @property
    def pixels_per_second(self)->float:return self._pps
    def set_timeline(self,items,selected=None):self._items=items;self._selected=set(selected or ());self._resize();self.update()
    def set_pixels_per_second(self,pps:float):self._pps=max(2.,min(1000.,pps));self._resize();self.update()
    def _resize(self):self.setMinimumWidth(max(640,int(sum(i.duration_ms for i in self._items)/1000*self._pps)+40))
    def set_position(self,ms:int):self._position_ms=max(0,ms);self.update()
    def _regions(self):
        start=0
        for index,item in enumerate(self._items):
            end=start+item.duration_ms;left=round(start*self._pps/1000);width=max(3,round(item.duration_ms*self._pps/1000));yield index,item,start,end,left,width;start=end
    def _hit(self,x):
        for value in self._regions():
            if value[4]<=x<=value[4]+value[5]:return value
        return None
    def _edge(self,x,hit):
        if not hit:return _Mode.NONE
        return _Mode.TRIM_LEFT if x-hit[4]<=self.EDGE else _Mode.TRIM_RIGHT if hit[4]+hit[5]-x<=self.EDGE else _Mode.MOVE
    def mouseMoveEvent(self,event):
        x=round(event.position().x())
        if self._mode is _Mode.NONE:
            edge=self._edge(x,self._hit(x));self.setCursor(Qt.CursorShape.SizeHorCursor if edge in (_Mode.TRIM_LEFT,_Mode.TRIM_RIGHT) else Qt.CursorShape.OpenHandCursor if edge is _Mode.MOVE else Qt.CursorShape.ArrowCursor);return
        if self._item is None:return
        delta=round((x-self._x)*1000/self._pps)
        if self._mode is _Mode.TRIM_LEFT:start=max(0,min(self._start+delta,self._end-1));end=self._end
        elif self._mode is _Mode.TRIM_RIGHT:start=self._start;limit=self._item.source_duration_ms if isinstance(self._item,AudioClip) else 86400000;end=max(start+1,min(self._end+delta,limit))
        else:return
        self.trim_preview.emit(self._item.clip_id,start,end)
    def mousePressEvent(self,event):
        x=round(event.position().x());hit=self._hit(x)
        if not hit:self._selected.clear();self.selection_changed.emit(set());self.seek_requested.emit(round(x*1000/self._pps));return
        _index,item,_start,_end,_left,_width=hit;self._selected= self._selected ^ {item.clip_id} if event.modifiers()&Qt.KeyboardModifier.ControlModifier else {item.clip_id};self.selection_changed.emit(set(self._selected));self._mode=self._edge(x,hit);self._item=item;self._x=x;self._start=item.trim_start_ms if isinstance(item,AudioClip) else 0;self._end=item.effective_end_ms if isinstance(item,AudioClip) else item.duration_ms
    def mouseReleaseEvent(self,event):
        if self._item and self._mode in (_Mode.TRIM_LEFT,_Mode.TRIM_RIGHT):
            delta=round((round(event.position().x())-self._x)*1000/self._pps)
            if self._mode is _Mode.TRIM_LEFT:start=max(0,min(self._start+delta,self._end-1));end=self._end
            else:start=self._start;limit=self._item.source_duration_ms if isinstance(self._item,AudioClip) else 86400000;end=max(start+1,min(self._end+delta,limit))
            self.trim_committed.emit(self._item.clip_id,start,end)
        elif self._item and self._mode is _Mode.MOVE:
            hit=self._hit(round(event.position().x()));self.move_committed.emit(set(self._selected),hit[0] if hit else len(self._items))
        self._mode=_Mode.NONE;self._item=None
    def wheelEvent(self,event:QWheelEvent):
        if event.modifiers()&Qt.KeyboardModifier.ControlModifier:self.zoom_requested.emit(1.2 if event.angleDelta().y()>0 else 1/1.2);event.accept()
        else:event.ignore()
    def paintEvent(self,event:QPaintEvent):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#101820'));left=event.rect().left();right=event.rect().right();visible_start=left*1000/self._pps;visible_end=right*1000/self._pps
        major=5000 if self._pps<20 else 1000 if self._pps<80 else 100 if self._pps<400 else 50;minor=max(1,major//5);start=int(visible_start//minor)*minor
        p.setPen(QColor('#506477'))
        for tick in range(start,int(visible_end)+minor,minor):
            x=round(tick*self._pps/1000);main=tick%major==0;p.drawLine(x,0,x,22 if main else 10)
            if main:p.drawText(x+3,18,format_ms(tick))
        for _,item,start,end,x,w in self._regions():
            if x+w<left or x>right:continue
            selected=item.clip_id in self._selected;p.fillRect(x,35,w,self.height()-48,QColor('#bb7a3d' if selected else '#414e5a' if isinstance(item,AudioClip) else '#273746'));p.setPen(QColor('#e6edf3'));p.drawRect(x,35,w,self.height()-48)
            mid=(35+self.height()-13)//2
            if isinstance(item,AudioClip):
                # Uses cached envelope attached by the waveform worker; fallback is a centre line.
                envelope=getattr(item,'waveform',())
                p.setPen(QColor('#9bbbd0'))
                if envelope:
                    for px in range(max(x,left),min(x+w,right)+1):
                        point=envelope[min(len(envelope)-1,max(0,round((px-x)/max(1,w)*(len(envelope)-1))))];p.drawLine(px,mid-int(point[0]*55),px,mid-int(point[1]*55))
                else:p.drawLine(x+4,mid,x+w-4,mid)
                p.drawText(x+7,57,f'{item.source_path.name}  {format_ms(item.trim_start_ms)}–{format_ms(item.effective_end_ms)}')
            else:p.setPen(QColor('#9bbbd0'));p.drawLine(x+4,mid,x+w-4,mid);p.drawText(x+7,57,f'\u7a7a\u767d {format_ms(item.duration_ms)}')
        x=round(self._position_ms*self._pps/1000);p.setPen(QPen(QColor('#e3a353'),2));p.drawLine(x,24,x,self.height());p.end()
