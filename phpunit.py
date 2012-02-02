import functools
import os
import re
import subprocess
import time
import thread
import sublime
import sublime_plugin

# the AsyncProcess class has been cribbed from:
# https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py

class AsyncProcess(object):
  def __init__(self, cmd, listener):
    self.cmd = cmd
    self.listener = listener
    print "DEBUG_EXEC: " + self.cmd
    self.proc = subprocess.Popen([self.cmd], shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if self.proc.stdout:
      thread.start_new_thread(self.read_stdout, ())
    if self.proc.stderr:
      thread.start_new_thread(self.read_stderr, ())

  def read_stdout(self):
    while True:
      data = os.read(self.proc.stdout.fileno(), 2**15)
      if data != "":
        sublime.set_timeout(functools.partial(self.listener.append_data, self.proc, data), 0)
      else:
        self.proc.stdout.close()
        self.listener.is_running = False
        break

  def read_stderr(self):
    while True:
      data = os.read(self.proc.stderr.fileno(), 2**15)
      if data != "":
        sublime.set_timeout(functools.partial(self.listener.append_data, self.proc, data), 0)
      else:
        self.proc.stderr.close()
        self.listener.is_running = False
        break

# the StatusProcess class has been cribbed from:
# https://github.com/maltize/sublime-text-2-ruby-tests/blob/master/run_ruby_test.py

class StatusProcess(object):
  def __init__(self, msg, listener):
    self.msg = msg
    self.listener = listener
    thread.start_new_thread(self.run_thread, ())

  def run_thread(self):
    progress = ""
    while True:
      if self.listener.is_running:
        if len(progress) >= 10:
          progress = ""
        progress += "."
        sublime.set_timeout(functools.partial(self.listener.update_status, self.msg, progress), 0)
        time.sleep(1)
      else:
        break

class OutputView(object):
    def __init__(self, name, view):
        self.output_name = name
        self.view = view

    def window(self):
        return self.view.window()

    def show_output(self):
        self.ensure_output_view()
        self.window().run_command("show_panel", {"panel": "output." + self.output_name})

    def show_empty_output(self):
        self.ensure_output_view()
        self.clear_output_view()
        self.show_output()

    def ensure_output_view(self):
        if not hasattr(self, 'output_view'):
            self.output_view = self.window().get_output_panel(self.output_name)

    def clear_output_view(self):
        self.ensure_output_view()
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.erase(edit, sublime.Region(0, self.output_view.size()))
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)

    def append_data(self, proc, data):
        str = data.decode("utf-8")
        str = str.replace('\r\n', '\n').replace('\r', '\n')

        selection_was_at_end = (len(self.output_view.sel()) == 1
          and self.output_view.sel()[0]
            == sublime.Region(self.output_view.size()))
        self.output_view.set_read_only(False)
        edit = self.output_view.begin_edit()
        self.output_view.insert(edit, self.output_view.size(), str)
        if selection_was_at_end:
          self.output_view.show(self.output_view.size())
        self.output_view.end_edit(edit)
        self.output_view.set_read_only(True)


class PhpunitBase(sublime_plugin.TextCommand):
    def show_output(self):
        if not hasattr(self, 'output_view'):
            self.output_view = OutputView('phpunit', self.view)

        self.output_view.show_output()

    def show_empty_output(self):
        if not hasattr(self, 'output_view'):
            self.output_view = OutputView('phpunit', self.view)

        self.output_view.clear_output_view()
        self.output_view.show_output()

    def is_php_buffer(self):
        # is this a PHP buffer?
        if re.search('.+\PHP.tmLanguage', self.view.settings().get('syntax')):
            return True
        return False

    def is_test_buffer(self):
        filename = os.path.splitext(os.path.basename(self.view.file_name()))[0]
        if filename.endswith('Test'):
            return True
        return False

    def start_async(self, caption, executable):
        self.is_running = True
        self.proc = AsyncProcess(executable, self)
        StatusProcess(caption, self)

    def append_data(self, proc, data):
        self.output_view.append_data(proc, data)

    def update_status(self, msg, progress):
        sublime.status_message(msg + " " + progress)

    def findPhpunitXml(self):
        dir_name = os.path.dirname(self.view.file_name())
        path = self.findFolderContainingFile(dir_name, 'phpunit.xml')
        if (path is not None):
            return path
        return self.findFolderContainingFile(dir_name, 'phpunit.xml.dist')

    def findFolderContainingFile(self, path, filename):
        if (path == ''):
            return None
        if (os.path.exists(path + '/' + filename)):
            return path

        return self.findFolderContainingFile(os.path.dirname(path), filename)

    def determineClassToTest(self):
        class_to_test = os.path.splitext(os.path.basename(self.view.file_name()))[0]
        if not class_to_test.endswith('Test'):
            class_to_test = class_to_test + "Test"

        return class_to_test

    def determineTestFile(self):
        filename = os.path.splitext(os.path.basename(self.view.file_name()))[0]
        if filename.endswith('Test'):
            return self.view.file_name()

        return None

class PhpunitTestThisClass(PhpunitBase):
    def run(self, args):
        dir_to_cd = self.findPhpunitXml()
        file_to_test = self.determineTestFile()

        if (dir_to_cd is None):
            sublime.status_message('Unable to find phpunit.xml or phpunit.xml.dist')
        else:
            self.show_empty_output()
            self.start_async("Running all tests", "cd '" + dir_to_cd + "' && phpunit '" + file_to_test + "'")

    def description(self):
        return 'Test This Class...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False
        if self.is_test_buffer():
            return False
        # for now, disable this command until it works
        return False

    def is_visible(self):
        return self.is_enabled()

class PhpunitRunTheseTests(PhpunitBase):
    def run(self, args):
        dir_to_cd = self.findPhpunitXml()
        file_to_test = self.determineTestFile()

        if (dir_to_cd is None):
            sublime.status_message('Unable to find phpunit.xml or phpunit.xml.dist')
        else:
            self.show_empty_output()
            self.start_async("Running tests", "cd '" + dir_to_cd + "' && phpunit '" + file_to_test + "'")

    def description(self):
        return 'Run These Tests...'

    def is_enabled(self):
        if not self.is_php_buffer():
            return False

        if not self.is_test_buffer():
            return False

        return True

    def is_visible(self):
        return self.is_enabled()

class PhpunitRunAllTestsCommand(PhpunitBase):
    def run(self, args):
        dir_to_cd = self.findPhpunitXml()
        if (dir_to_cd is None):
            sublime.status_message('Unable to find phpunit.xml or phpunit.xml.dist')
        else:
            self.show_empty_output()
            self.start_async("Running all tests", "cd '" + dir_to_cd + "' && phpunit")

    def description(self):
        return 'Run All Unit Tests...'

    def is_enabled(self):
        return self.is_php_buffer()

    def is_visible(self):
        return self.is_enabled()

class PhpunitShowOutputCommand(PhpunitBase):
    def run(self, args):
        self.show_output()

    def description(self):
        return 'Show Test Output...'

class PhpunitNotAvailableCommand(PhpunitBase):
    def is_visible(self):
        if not self.is_php_buffer():
            return True
        return False

    def is_enabled(self):
        return False

    def description(self):
        return 'PHPUnit tests can only be run on PHP windows'