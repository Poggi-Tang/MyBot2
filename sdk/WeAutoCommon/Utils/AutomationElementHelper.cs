using FlaUI.Core.AutomationElements;

namespace WeAutoCommon.Utils
{

    public static class AutomationElementHelper
    {
        /// <summary>
        /// 从元素的Name获得实际的昵称
        /// 适用于这些的字符串:
        /// 前端攻城狮
        /// [13条] 
        /// "西格玛学长" 拍了拍 "Hihi"
        /// 18:06
        /// </summary>
        /// <param name="element"></param>
        /// <returns></returns>
        public static string GetName(this AutomationElement element)
        {
            string[] aryItems = element.Name.Split('\n');
            var name = aryItems[0].Trim();
            return name;
        }
    }
}
