// Runs the bridge's MCP server outside OpenRoads Designer, for tests: bimai-openroads-dev.exe <port>.
// The civil tools answer that OpenRoads' API isn't available; the protocol is the real one.
using System;
using System.Threading;

namespace Bimai.OpenRoads
{
    public static class DevHost
    {
        public static int Main(string[] args)
        {
            int port = args.Length > 0 ? int.Parse(args[0]) : 0;
            var log = new Log(System.IO.Path.Combine(System.IO.Path.GetTempPath(), "bimai-openroads-dev.log"));
            var dispatcher = new InlineDispatcher();
            var bridge = Bridge.Start(dispatcher, CivilTools.Create(dispatcher), log, port);
            if (bridge.StartError != null)
            {
                Console.Error.WriteLine(bridge.StartError);
                return 1;
            }
            Console.WriteLine("listening " + bridge.Server.Port);
            Console.Out.Flush();
            Thread.Sleep(Timeout.Infinite);
            return 0;
        }
    }
}
