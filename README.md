# 科迪 · 抖音插件

Kodi 插件 `plugin.video.douyin` **1.5.11**（Cookie 登录版，搜索修复）。

仓库：[hxw885210-cmd/kodi](https://github.com/hxw885210-cmd/kodi)

## 下载安装包

点这个文件下载：

**[plugin.video.douyin-1.5.11.zip](https://github.com/hxw885210-cmd/kodi/raw/main/plugin.video.douyin-1.5.11.zip)**

## 装到 Kodi

1. Kodi → 系统 → 加载项 → 打开「未知来源」
2. 插件 → 从 ZIP 文件安装 → 选刚下的 `plugin.video.douyin-1.5.11.zip`
3. 视频插件里打开「抖音」
4. 用电脑浏览器登录 [douyin.com](https://www.douyin.com)，把 Cookie / `sessionid` 粘进插件登录页

没登录时，抖音会直接拒绝搜索。

## 1.5.11 搜索修复

- 以前很多词会空白：接口空结果被当成成功、只认热搜词、H.265 / 缺播放地址的视频被丢掉
- 现在会连试视频搜索、综合搜索、用户搜索
- 作者名会先出用户卡片，再进主页作品
- 综合结果里带视频、用户、直播；排序和发布时间筛选还在
- 推荐、直播、关注、喜欢、遥控连播没改

## 目录

```
plugin.video.douyin/                 插件源码
plugin.video.douyin-1.5.11.zip       Kodi 安装包
```

分支 `plugin.video.douyin` 与主分支内容相同，专门放这个插件。
