using System;
using System.Threading;
using System.Windows.Forms;

namespace Bimai.OpenRoads
{
    /// <summary>
    /// Runs work on OpenRoads Designer's main thread, where Bentley's APIs must be called. A hidden control
    /// created on that thread receives the work through BeginInvoke, which posts a window message that
    /// OpenRoads' message loop runs promptly. The waiting connection thread gives up after the timeout;
    /// work that starts after that is skipped.
    /// </summary>
    public sealed class MainThreadDispatcher : IDispatcher, IDisposable
    {
        private readonly Control _control;
        private readonly TimeSpan _timeout;
        private volatile bool _disposed;

        /// <summary>Must be constructed on the main thread (in AddIn.Run).</summary>
        public MainThreadDispatcher(TimeSpan timeout)
        {
            _timeout = timeout;
            _control = new Control();
            _control.CreateControl();
            IntPtr handle = _control.Handle;    // forces the window handle to exist on this thread
            GC.KeepAlive(handle);
        }

        public T Invoke<T>(Func<T> work)
        {
            if (_disposed) throw new ToolException("The bimai OpenRoads bridge is shutting down.");
            T result = default(T);
            Exception error = null;
            int state = 0;                      // 0 waiting, 1 started, 2 abandoned
            using (var done = new ManualResetEvent(false))
            {
                try
                {
                    _control.BeginInvoke(new Action(() =>
                    {
                        if (Interlocked.CompareExchange(ref state, 1, 0) != 0) return;     // the caller gave up
                        try { result = work(); }
                        catch (Exception ex) { error = ex; }
                        finally
                        {
                            try { done.Set(); } catch (ObjectDisposedException) { }
                        }
                    }));
                }
                catch (Exception)
                {
                    throw new ToolException("The bimai OpenRoads bridge is shutting down.");
                }
                if (!done.WaitOne(_timeout))
                {
                    if (Interlocked.CompareExchange(ref state, 2, 0) == 0)
                        throw new ToolException("OpenRoads Designer did not respond within " + (int)_timeout.TotalSeconds +
                                                " seconds. It may be busy (a dialog box open, or a long operation running). " +
                                                "Try again when OpenRoads is idle.");
                    done.WaitOne();             // it started just now: wait for it to finish
                }
            }
            if (error != null)
            {
                if (error is ToolException) throw error;
                throw new System.Reflection.TargetInvocationException(error);   // McpServer reports the inner error
            }
            return result;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _disposed = true;
            try { _control.Dispose(); } catch (Exception) { }
        }
    }
}
