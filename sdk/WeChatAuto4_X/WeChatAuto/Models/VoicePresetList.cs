using System.Collections.Generic;
using NAudio.Wave;
using WeChatAuto.Models;

namespace WeChatAuto.Models;

/// <summary>
/// 预设音色列表
/// </summary>
public static class VoicePresetList
{
    public static List<VoicePreset> AllVoicePresets
    {
        get
        {
            return new List<VoicePreset>()
            {
              new VoicePreset {Id="Cherry",Description="阳光积极、亲切自然小姐姐（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Serena",Description="温柔小姐姐（女性）",MainLanguage = "普通话"},
              new VoicePreset {Id="Ethan",Description="标准普通话，带部分北方口音。阳光、温暖、活力、朝气（男性）",MainLanguage = "普通话"},
              new VoicePreset {Id="Chelsie",Description="二次元虚拟女友（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Momo",Description="撒娇搞怪，逗你开心（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Vivian",Description="拽拽的、可爱的小暴躁（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Moon",Description="率性帅气的月白（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Maia",Description="知性与温柔的碰撞（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Kai",Description="耳朵的一场SPA（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Nofish",Description="不会翘舌音的设计师（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Bella",Description="喝酒不打醉拳的小萝莉（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Jennifer",Description="品牌级、电影质感般美语女声（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Ryan",Description="节奏拉满，戏感炸裂，真实与张力共舞（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Katerina",Description="御姐音色，韵律回味十足（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Aiden",Description="精通厨艺的美语大男孩（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Eldric Sage",Description="沉稳睿智的老者，沧桑如松却心明如镜（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Mia",Description="温顺如春水，乖巧如初雪（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Mochi",Description="聪明伶俐的小大人，童真未泯却早慧如禅（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Bellona",Description="声音洪亮，吐字清晰，人物鲜活，听得人热血沸腾；金戈铁马入梦来，字正腔圆间尽显千面人声的江湖（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Vincent",Description="一口独特的沙哑烟嗓，一开口便道尽了千军万马与江湖豪情（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Bunny",Description="“萌属性”爆棚的小萝莉（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Neil",Description="平直的基线语调，字正腔圆的咬字发音，这就是最专业的新闻主持人（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Elias",Description="既保持学科严谨性，又通过叙事技巧将复杂知识转化为可消化的认知模块（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Arthur",Description="被岁月和旱烟浸泡过的质朴嗓音，不疾不徐地摇开了满村的奇闻异事（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Nini",Description="糯米糍一样又软又黏的嗓音，那一声声拉长了的“哥哥”，甜得能把人的骨头都叫酥了（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Seren",Description="温和舒缓的声线，助你更快地进入睡眠，晚安，好梦（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Pip",Description="调皮捣蛋却充满童真的他来了，这是你记忆中的小新吗（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Stella",Description="平时是甜到发腻的迷糊少女音，但在喊出“代表月亮消灭你”时，瞬间充满不容置疑的爱与正义（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Bodega",Description="热情的西班牙大叔（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Sonrisa",Description="热情开朗的拉美大姐（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Alek",Description="一开口，是战斗民族的冷，也是毛呢大衣下的暖（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Dolce",Description="慵懒的意大利大叔（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Sohee",Description="温柔开朗，情绪丰富的韩国欧尼（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Ono Anna",Description="鬼灵精怪的青梅竹马（女性）",MainLanguage="普通话"},
              new VoicePreset {Id="Lenn",Description="理性是底色，叛逆藏在细节里——穿西装也听后朋克的德国青年（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Emilien",Description="浪漫的法国大哥哥（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Andre",Description="声音磁性，自然舒服、沉稳男生（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Radio Gol",Description="足球诗人Rádio Gol！今天我要用名字为你们解说足球（男性）",MainLanguage="普通话"},
              new VoicePreset {Id="Jada",Description="风风火火的沪上阿姐（女性）",MainLanguage="上海话"},
              new VoicePreset {Id="Dylan",Description="北京胡同里长大的少年（男性）",MainLanguage="北京话"},
              new VoicePreset {Id="Li",Description="耐心的瑜伽老师（男性）",MainLanguage="南京话"},
              new VoicePreset {Id="Marcus",Description="面宽话短，心实声沉——老陕的味道（男性）",MainLanguage="陕西话"},
              new VoicePreset {Id="Roy",Description="诙谐直爽、市井活泼的台湾哥仔形象（男性）",MainLanguage="闽南语"},
              new VoicePreset {Id="Peter",Description="天津相声，专业捧哏（男性）",MainLanguage="天津话"},
              new VoicePreset {Id="Sunny",Description="甜到你心里的川妹子（女性）",MainLanguage="四川话"},
              new VoicePreset {Id="Eric",Description="一个跳脱市井的四川成都男子（男性）",MainLanguage="四川话"},
              new VoicePreset {Id="Rocky",Description="幽默风趣的阿强，在线陪聊（男性）",MainLanguage="粤语"},
              new VoicePreset {Id="Kiki",Description="甜美的港妹闺蜜（女性）",MainLanguage="粤语"},
            };
        }
    }
}