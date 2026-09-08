## 1. Create ConsoleWidget Component

- [x] 1.1 Add `ConsoleWidget` class in ui.py (around line 800, after LogWidget)
- [x] 1.2 Implement `__init__()` with VBoxLayout, header label "▾ CONSOLE OUTPUT", and Clear button
- [x] 1.3 Add QTextEdit display with read-only, Courier New 7pt, no line wrap, styled with C.BG background
- [x] 1.4 Implement `_sig` pyqtSignal for thread-safe text appending (signature: str, object for text and color)
- [x] 1.5 Implement `append_text(text, color)` method that emits signal
- [x] 1.6 Implement `_append(text, color)` slot that inserts text with color formatting into QTextEdit
- [x] 1.7 Implement auto-trim logic: when lineCount() > 1000, delete oldest lines
- [x] 1.8 Implement `_clear()` slot connected to Clear button that calls `self._display.clear()`
- [x] 1.9 Apply scrollbar styling matching LogWidget style (6px width, BORDER_B handle)

## 2. Create ConsoleRedirector Stream

- [x] 2.1 Add `ConsoleRedirector` class in ui.py (before ConsoleWidget)
- [x] 2.2 Implement `__init__(text_widget, color, original_stream)` storing references and initializing buffer
- [x] 2.3 Add `_buffer` list and `_timer` QTimer that fires every 100ms
- [x] 2.4 Implement `write(text)` method that appends to buffer and writes to original stream
- [x] 2.5 Add buffer flush on >50 messages accumulated (emergency flush)
- [x] 2.6 Implement `_flush_buffer()` that combines buffered text and calls `text_widget.append_text()`
- [x] 2.7 Implement `flush()` method that calls `original.flush()` if available
- [x] 2.8 Connect timer timeout to `_flush_buffer()`

## 3. Refactor Right Panel to Use QSplitter

- [x] 3.1 In `_build_right_panel()`, create QSplitter(Qt.Orientation.Vertical) instead of returning widget directly
- [x] 3.2 Create activity_log_widget (QWidget with VBoxLayout containing "▸ ACTIVITY LOG" label and LogWidget)
- [x] 3.3 Add activity_log_widget to splitter as first widget
- [x] 3.4 Create ConsoleWidget instance and add to splitter as second widget
- [x] 3.5 Set stretch factors: `setStretchFactor(0, 3)` for Activity Log, `setStretchFactor(1, 1)` for Console
- [x] 3.6 Set collapsible flags: `setCollapsible(0, False)` for Activity Log, `setCollapsible(1, True)` for Console
- [x] 3.7 Apply splitter stylesheet matching center splitter (4px handle, transparent, PRI_DIM on hover)
- [x] 3.8 Initialize with Console collapsed: `setSizes([total_height, 0])` where total_height is estimate
- [x] 3.9 Add splitter to main right panel VBoxLayout with stretch=1
- [x] 3.10 Keep FILE UPLOAD, COMMAND INPUT, and buttons sections below splitter unchanged

## 4. Setup stdout/stderr Redirection

- [x] 4.1 In `JarvisMainWindow.__init__()`, store `self._console_widget` reference after building right panel
- [x] 4.2 After UI is fully initialized, save `self._original_stdout = sys.stdout` and `self._original_stderr = sys.stderr`
- [x] 4.3 Create ConsoleRedirector for stdout: `sys.stdout = ConsoleRedirector(self._console_widget, QColor(C.TEXT), self._original_stdout)`
- [x] 4.4 Create ConsoleRedirector for stderr: `sys.stderr = ConsoleRedirector(self._console_widget, QColor(C.RED), self._original_stderr)`
- [x] 4.5 Add import for `sys` at top of ui.py if not already present

## 5. Cleanup and Restoration

- [x] 5.1 In `closeEvent()` method of JarvisMainWindow, restore original streams: `sys.stdout = self._original_stdout`
- [x] 5.2 Restore stderr: `sys.stderr = self._original_stderr`
- [x] 5.3 Add safety check: only restore if `_original_stdout` and `_original_stderr` attributes exist

## 6. Visual Polish and Theme Integration

- [x] 6.1 Verify ConsoleWidget header uses consistent font and color with other section headers (_sec style)
- [x] 6.2 Ensure Clear button matches dismiss button style from Content Panel (7pt font, small height)
- [x] 6.3 Test theme color changes: verify Console Output updates colors when user changes UI theme
- [x] 6.4 Verify scrollbar in Console matches Activity Log scrollbar style

## 7. Testing and Verification

- [ ] 7.1 Test: Launch app, verify Console Output starts collapsed and Activity Log has full space
- [ ] 7.2 Test: Drag splitter handle down, verify Console expands and Activity Log shrinks smoothly
- [ ] 7.3 Test: Drag splitter to bottom, verify Console collapses completely
- [ ] 7.4 Test: Add `print("test stdout")` in main.py startup, verify it appears in Console Output
- [ ] 7.5 Test: Trigger an exception, verify traceback appears in Console Output in red color
- [ ] 7.6 Test: Verify print() output also appears in terminal/console where app was launched
- [ ] 7.7 Test: Expand Console, click Clear button, verify content is cleared
- [ ] 7.8 Test: Spam 100 print() statements rapidly, verify UI remains responsive and messages batch correctly
- [ ] 7.9 Test: Let Console accumulate >1000 lines, verify auto-trim removes oldest lines
- [ ] 7.10 Test: Unicode/emoji in print statements, verify they display correctly in Console Output
- [ ] 7.11 Test: Background thread executes print(), verify message appears without crash
- [ ] 7.12 Test: Close application, verify sys.stdout/stderr are restored (check no errors on exit)

## 8. Documentation

- [x] 8.1 Add docstring to ConsoleWidget explaining purpose and thread-safety
- [x] 8.2 Add docstring to ConsoleRedirector explaining stream redirection and buffering strategy
- [x] 8.3 Add comment in `_build_right_panel()` explaining splitter configuration (similar to center splitter)
- [x] 8.4 Add comment about 1000-line limit and why it's necessary
