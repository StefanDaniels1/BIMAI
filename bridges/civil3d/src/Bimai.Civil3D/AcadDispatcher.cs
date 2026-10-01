using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Bimai.Mcp;

namespace Bimai.Civil3D;

/// <summary>
/// Runs work on Civil 3D's main thread. A hidden control created on that thread receives the work via
/// BeginInvoke, which posts a window message: the work runs promptly in the application context, even
/// when the user isn't touching anything (AutoCAD's Idle event only fires after input).
/// The waiting side gives up after the timeout; work that starts after that is skipped.
/// </summary>
internal sealed class AcadDispatcher : IHostDispatcher, IDisposable
{
    private readonly Control _control;
    private readonly TimeSpan _timeout;
    private volatile bool _disposed;

    /// <summary>Must be constructed on Civil 3D's main thread (IExtensionApplication.Initialize).</summary>
    public AcadDispatcher(TimeSpan timeout)
    {
        _timeout = timeout;
        _control = new Control();
        _control.CreateControl();
        _ = _control.Handle;    // forces the window handle to exist on this thread
    }

    public async Task<T> InvokeAsync<T>(Func<T> work, CancellationToken cancellationToken)
    {
        if (_disposed) throw new ToolException("The bimai Civil 3D bridge is shutting down.");
        var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        try
        {
            _control.BeginInvoke(new Action(() =>
            {
                if (tcs.Task.IsCompleted) return;               // the caller already gave up
                try { tcs.TrySetResult(work()); }
                catch (Exception ex) { tcs.TrySetException(ex); }
            }));
        }
        catch (Exception ex) when (ex is InvalidOperationException or ObjectDisposedException)
        {
            throw new ToolException("The bimai Civil 3D bridge is shutting down.");
        }

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(_timeout);
        var finished = await Task.WhenAny(tcs.Task, Task.Delay(Timeout.Infinite, timeout.Token)).ConfigureAwait(false);
        if (finished != tcs.Task)
        {
            tcs.TrySetCanceled();
            throw new ToolException($"Civil 3D did not respond within {_timeout.TotalSeconds:0} seconds. It may be busy " +
                                    "(a dialog box open, or a long operation running). Try again when Civil 3D is idle.");
        }
        return await tcs.Task.ConfigureAwait(false);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        try { _control.Dispose(); } catch (Exception) { }
    }
}
